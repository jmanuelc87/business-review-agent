import pathlib

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, SecretStr, Field

from typing import List
from typing_extensions import TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langgraph.graph import StateGraph
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document
from langchain_tavily.tavily_search import TavilySearch
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_openai import OpenAIEmbeddings

md_text_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[
        ("#", "header1"),
        ("##", "header2"),
        ("###", "header3"),
    ],
    strip_headers=False,
)


path = pathlib.Path("files/docs_rag")

docs = []
for file in path.glob("*.md"):
    loader = TextLoader(file, autodetect_encoding=True)
    docs.append(loader.load())

docs_split = []
for doc in docs:
    docs_split.extend(md_text_splitter.split_text(doc[0].page_content))


vectorstore = Chroma.from_documents(
    documents=docs_split,
    collection_name="rag_docs_chroma",
    collection_metadata={"hnsw:space": "cosine"},
    embedding=OpenAIEmbeddings(
        base_url="http://127.0.0.1:1234/v1",
        model="text-embedding-nomic-embed-text-v1.5",
        api_key=SecretStr("sk-lm-VHP9fraW:FFrUFeg4YVCY4T5lKwcu"),
        check_embedding_ctx_length=False,
    ),
)

retriever = vectorstore.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"score_threshold": 0.6, "k": 100},
)


## Retrieve Evaluator


class RetrievalEvaluator(BaseModel):
    """Classify retrieved documents based on how relevant it is to the user's question."""

    binary_evaluation: str = Field(
        description="Documents are relevant to the question, 'yes' or 'no'"
    )


retrieval_evaluator = create_agent(
    model="gpt-5.4-nano-2026-03-17",
    response_format=RetrievalEvaluator,
    system_prompt=(
        "You are a document retrieval evaluator that's responsible for checking the relevancy of a retrieved document to the user's question. "
        "If the document contains keyword(s) or semantic meaning related to the question, grade it as relevant. "
        "Output a binary score 'yes' or 'no' to indicate whether the document is relevant to the question. "
    ),
)


## Question Rewriter

question_rewriter = create_agent(
    model="gpt-5.4-nano-2026-03-17",
    system_prompt="""You are a question re-writer that converts an input question to a better version that is optimized for RAG search. 
    Look at the input and try to reason about the underlying semantic intent / meaning.""",
)


## Agent RAG Assistant


@dynamic_prompt
def build_prompt(request) -> str:
    ctx = request.runtime.context
    return (
        "You are an assistant for question-answering tasks. Use the following "
        "retrieved context to answer. If you don't know, say so. Three sentences max.\n"
        f"Context: {ctx}"
    )


agent = create_agent(
    model="gpt-5.4-nano-2026-03-17",
    middleware=[build_prompt],
)

## Web Search Tool

web_search_tool = TavilySearch(
    k=30,
    topic="general",
)

# StateGraph


class RagState(TypedDict):
    question: str
    generation: str
    web_search: str
    documents: List[str]


## Graph Nodes


def retrieve(state):
    question = state["question"]
    documents = retriever.invoke(question)
    return {"documents": documents, "question": question}


def generate(state):
    question = state["question"]
    documents = state["documents"]

    generation = agent.invoke(
        {"messages": [{"role": "user", "content": question}]}, context={"documents": documents}  # type: ignore
    )

    return {
        "documents": documents,
        "question": question,
        "generation": generation["messages"][-1].content,
    }


def grade_documents(state):
    question = state["question"]
    documents = state["documents"]

    web_search = "No"

    filtered_docs = []
    for document in documents:
        prompt = (
            f"Retrieved document: \\n\\n {document} \\n\\n User question: {question}"
        )
        score = retrieval_evaluator.invoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )

        if score["structured_response"].binary_evaluation.lower() == "yes":
            filtered_docs.append(document)
        else:
            continue

    if len(documents) > 0 and len(filtered_docs) / len(documents) <= 0.25:
        web_search = "Yes"

    return {"documents": filtered_docs, "question": question, "web_search": web_search}


def transform_query(state):
    question = state["question"]
    documents = state["documents"]

    prompt = f"Here is the initial question: \n\n {question} \n Formulate an improved question."

    better_question = question_rewriter.invoke(
        {"messages": [{"role": "user", "content": prompt}]}
    )

    return {"documents": documents, "question": better_question["messages"][-1].content}


def web_search(state):
    question = state["question"]
    documents = state["documents"]

    searched = web_search_tool.invoke({"query": question})

    web_results = "\\n".join([d["content"] for d in searched["results"]])
    web_results = Document(page_content=web_results)
    documents.append(web_results)

    return {"documents": documents, "question": question}


def decide_to_generate(state):
    web_search = state["web_search"]

    if web_search.lower() == "yes":
        return "transform_query"
    else:
        return "generate"


## Graph Definition

workflow = StateGraph(RagState)
workflow.add_node("retrieve", retrieve)
workflow.add_node("grade_documents", grade_documents)
workflow.add_node("generate", generate)
workflow.add_node("transform_query", transform_query)
workflow.add_node("web_search", web_search)


workflow.add_edge("__start__", "retrieve")
workflow.add_edge("retrieve", "grade_documents")
workflow.add_conditional_edges(
    "grade_documents",
    decide_to_generate,
    {
        "transform_query": "transform_query",
        "generate": "generate",
    },
)
workflow.add_edge("transform_query", "web_search")
workflow.add_edge("web_search", "generate")
workflow.add_edge("generate", "__end__")


app = workflow.compile()
