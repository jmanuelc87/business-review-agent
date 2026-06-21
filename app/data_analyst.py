from dotenv import load_dotenv

load_dotenv()


import langgraph.graph
from typing_extensions import TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt, Command
from langchain_core.tools import tool
from langchain_openai.chat_models import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit

# Data Analyst Agent

db = SQLDatabase.from_uri(f"sqlite:///files/qbr.db")


model = ChatOpenAI(
    model="gpt-5.4-nano-2026-03-17",
)

toolkit = SQLDatabaseToolkit(db=db, llm=model)
tools = toolkit.get_tools()


sql_query_tool = next(t for t in toolkit.get_tools() if t.name == "sql_db_query")


@tool("db_query_with_interrupt")
def db_query_with_interrupt(query: str) -> str:
    """Run a SQL query against the database after human review."""

    result = interrupt(
        {
            "question": "Do you want to execute the following query? [y/n]",
            "tool": "sql_db_query",
            "args": {"query": query},
        }
    )

    if result["approve"].lower() == "y":
        return sql_query_tool.invoke({"query": result["query"]})
    else:
        return "Query execution canceled by the user."


SYSTEM_PROMPT = """
You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct {dialect} query to run,
then look at the results of the query and return the answer. Unless the user
specifies a specific number of examples they wish to obtain, always limit your
query to at most {top_k} results.

You can order the results by a relevant column to return the most interesting
examples in the database. Never query for all the columns from a specific table,
only ask for the relevant columns given the question.

You MUST double check your query before executing it. If you get an error while
executing a query, rewrite the query and try again.

DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the
database.

To start you should ALWAYS look at the tables in the database to see what you
can query. Do NOT skip this step.

Then you should query the schema of the most relevant tables.
"""


custom_tools = [t for t in toolkit.get_tools() if t.name != "sql_db_query"] + [
    db_query_with_interrupt
]

agent = create_agent(
    model,
    tools=custom_tools,
    system_prompt=SYSTEM_PROMPT.format(dialect=db.dialect, top_k=25),
)


# StateGraph


class SqlState(TypedDict):
    question: str
    generation: str


# Graph Nodes


def ask_to_analyst(state):
    question = state["question"]
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return {"question": question, "generation": result["messages"][-1].content}


def route_from_analyst(state):
    last = getattr(state, "messages", [{}])[-1]
    if getattr(last, "tool_calls", None):
        return "custom_tools"
    return "__end__"


# Graph Definition

workflow = StateGraph(SqlState)
workflow.add_node("ask_to_analyst", ask_to_analyst)
workflow.add_node("custom_tools", ToolNode(custom_tools))


workflow.add_edge("__start__", "ask_to_analyst")
workflow.add_edge("custom_tools", "ask_to_analyst")
workflow.add_conditional_edges(
    "ask_to_analyst",
    route_from_analyst,
    {"tools": "custom_tools", "__end__": "__end__"},
)


app = workflow.compile()
