import operator

from dotenv import load_dotenv

load_dotenv()

from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.graph import StateGraph
from langgraph.types import Send

from context_retriever import app as context_retriever_agent, build_prompt, workflow
from data_analyst import app as data_analyst_agent, SYSTEM_PROMPT

# Router Agent


class Classification(TypedDict):
    """A single routing decision: which agent to call with what query."""

    source: Literal["context_retriever", "data_analyst"]
    query: str


class ClassificationResult(BaseModel):
    """Result of classifying a user query into agent-specific sub-questions"""

    classifications: list[Classification] = Field(
        description="List of agents to invoke with their targeted sub-questions"
    )


SYSTEM_PROMPT = """Analyze this query and determine which knowledge bases to consult.
For each relevant source, generate a targeted sub-question optimized for that source.

the analyst text-to-SQL finds the *what* (the numbers) and RAG finds the *why* (tickets + notes)

Available sources:
 - context_retriever: search in the `support tickets` with the following unstructured metadata Date, Category, Priority and Description
 - data_analyst: search in the database using SQL with the following structured data `accounts`, `subscriptions`, `invoices`, `usage_monthly`, `account_health`
"""

router_agent = create_agent(
    model="gpt-5.4-mini-2026-03-17",
    system_prompt=SYSTEM_PROMPT,
    response_format=ClassificationResult,
)


# Synth Agent


@dynamic_prompt
def build_prompt(request) -> str:
    query = request.runtime.context["query"]
    return f"""Synthesize these search results to answer the original question: "{query}"

    - Combine information from multiple sources without redundancy
    - Highlight the most relevant and actionable information
    - Note any discrepancies between sources
    - Keep the response concise and well-organized"""


synth_agent = create_agent(
    model="gpt-5.4-mini-2026-03-17",
    middleware=[build_prompt],
)

# GraphState


class AgentInput(TypedDict):
    """Simple input state for each agent"""

    query: str


class AgentOutput(TypedDict):
    """Output from each subagent."""

    source: str
    result: str


class RouterState(TypedDict):
    query: str
    classifications: list[Classification]
    results: Annotated[
        list[AgentOutput],
        operator.add,
    ]
    final_answer: str


# Graph Nodes


def classify_query(state):

    result = router_agent.invoke(
        {"messages": [{"role": "user", "content": state["query"]}]}
    )

    return {"classifications": result["structured_response"].classifications}


def route_to_agents(state):
    return [Send(c["source"], {"query": c["query"]}) for c in state["classifications"]]


def query_context_retriever(state: AgentInput):

    result = context_retriever_agent.invoke(
        {
            "question": state["query"],
            "documents": [],
            "generation": "",
            "web_search": "",
        }
    )

    return {
        "results": [
            {
                "source": "context_retriever",
                "result": result["generation"],
            }
        ]
    }


def query_data_analyst(state: AgentInput):

    result = data_analyst_agent.invoke({"question": state["query"], "generation": ""})

    return {
        "results": [
            {
                "source": "data_analyst",
                "result": result["generation"],
            }
        ]
    }


def synthesize_results(state: RouterState) -> dict:
    """Combine results from all agents into a coherent answer."""

    if not state["results"]:
        return {"final_answer": "No results found from any knowledge source."}

    # Format results for synthesis
    formatted = [
        f"**From {r['source'].title()}:**\n{r['result']}" for r in state["results"]
    ]

    response = synth_agent.invoke(
        {
            "messages": [
                {"role": "user", "content": "\n\n".join(formatted)},
            ]
        },
        context={"query": state["query"]},  # type: ignore
    )

    return {"final_answer": response["messages"][-1].content}


# Graph Definition

workflow = StateGraph(RouterState)
workflow.add_node("classify", classify_query)
workflow.add_node("context_retriever", query_context_retriever)
workflow.add_node("data_analyst", query_data_analyst)
workflow.add_node("synthesize", synthesize_results)

workflow.add_edge("__start__", "classify")
workflow.add_conditional_edges(
    "classify",
    route_to_agents,
    ["context_retriever", "data_analyst"],
)
workflow.add_edge("context_retriever", "synthesize")
workflow.add_edge("data_analyst", "synthesize")
workflow.add_edge("synthesize", "__end__")


checkpointer = InMemorySaver()
store = InMemoryStore()

app = workflow.compile(checkpointer=checkpointer, store=store)
