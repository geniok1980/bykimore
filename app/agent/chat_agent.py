from datetime import datetime
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from mem0 import Memory
from qdrant_client import QdrantClient

from app.agent.langgraph_agent import get_graph, create_initial_state
from app.agent.tools.ui_demo_tool import UIDemoTool
from app.core.config import settings
from app.schemas.chat import ChatResponse
from app.services.vector_store import MultiTenantVectorStore
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AISupport:
    _instance = None

    def __new__(cls, vector_store: MultiTenantVectorStore | None):
        if cls._instance is None:
            cls._instance = super(AISupport, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, vector_store: MultiTenantVectorStore | None):
        """
        Initialize the AI Support with Memory Configuration and Langchain OpenAI Chat Model.
        """
        if not hasattr(self, '_initialized') or not self._initialized:
            self._initialized = True

        self.__vector_store = vector_store
        self.__memory = None
        
        # Try to initialize memory with Qdrant, fallback to None if unavailable
        try:
            custom_prompt = """
                    Please extract relevant entities containing user information, preferences, context, and important facts that would help personalize future interactions. 
                    Here are some few shot examples:

                    Input: Hi.
                    Output: {{"facts" : []}}

                    Input: The weather is nice today.
                    Output: {{"facts" : []}}

                    Input: I'm a software developer working on Python projects and I prefer using FastAPI.
                    Output: {{"facts" : ["User is a software developer", "Works with Python", "Prefers FastAPI framework"]}}

                    Input: My name is John Smith, I live in New York and I'm interested in machine learning.
                    Output: {{"facts" : ["User name: John Smith", "Lives in New York", "Interested in machine learning"]}}

                    Input: I usually work late hours and prefer getting notifications in the evening.
                    Output: {{"facts" : ["Works late hours", "Prefers evening notifications"]}}

                    Input: I have experience with React and Node.js, but I'm new to TypeScript.
                    Output: {{"facts" : ["Experienced with React", "Experienced with Node.js", "New to TypeScript"]}}

                    Input: I'm planning a trip to Japan next month and need help with travel recommendations.
                    Output: {{"facts" : ["Planning trip to Japan", "Trip scheduled for next month", "Needs travel recommendations"]}}

                    Input: I'm a vegetarian and I'm allergic to nuts.
                    Output: {{"facts" : ["User is vegetarian", "Allergic to nuts"]}}

                    Input: I prefer dark mode interfaces and I use VS Code as my main editor.
                    Output: {{"facts" : ["Prefers dark mode interfaces", "Uses VS Code editor"]}}

                    Return the facts and user information in a json format as shown above.
                    """

            client = QdrantClient(settings.QDRANT_HOST, port=settings.QDRANT_PORT)

            config = {
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": "gpt-4o-mini",
                        "temperature": 0.1,
                        "max_tokens": 2000,
                        "api_key": settings.OPENAI_API_KEY
                    }
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": "text-embedding-3-small",
                        "embedding_dims": 768,
                        "api_key": settings.OPENAI_API_KEY
                    }
                },
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": "general_chat_history",
                        "embedding_model_dims": 768,
                        "client": client
                    }
                },
                "custom_prompt": custom_prompt,
                "version": "v1.1",
            }

            self.__memory = Memory.from_config(config)
            logger.info("Memory initialized with Qdrant")
        except Exception as e:
            logger.warning(f"Memory initialization failed, continuing without memory: {e}")
            self.__memory = None
            
        self.__app_id = "AI-general-chatbot"
        
        # Initialize graph with error handling for MCP connections
        try:
            self.__graph: CompiledStateGraph = get_graph()
            logger.info("LangGraph with MCP tools initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize LangGraph with MCP tools: {e}")
            # For now, we'll still fail if graph initialization fails completely
            # In a production environment, you might want to create a fallback graph
            raise

    async def ask(self, question: str, user_id: str, chat_id: str, tenant_id: str) -> dict:
        """Process a user question and return an AI response.
        
        Args:
            question: The user's question
            user_id: User identifier for personalization
            chat_id: Chat session identifier
            tenant_id: Tenant identifier for multi-tenant isolation
            
        Returns:
            Dictionary containing the AI response messages
        """
        logger.info("Self ID: {}".format(id(self)))

        memories = await self.__search_memory(question, user_id=user_id)

        relevant_docs = []
        if self.__vector_store:
            try:
                relevant_docs = self.__vector_store.get_chat_by_id(
                    chat_id=chat_id, 
                    user_id=user_id, 
                    tenant_id=tenant_id
                )
                logger.info(f"Retrieved {relevant_docs}")
            except Exception as e:
                logger.warning(f"Failed to retrieve chat history: {e}")
                relevant_docs = []

        context = "Relevant information from previous conversations:\n"
        if memories['results']:
            for memory in memories['results']:
                context += f" - {memory['memory']}\n"
        
        if relevant_docs:
            context += "\nRelevant chat history:\n"
            for i, doc in enumerate(relevant_docs):
                question_text = doc.get("user_message", "")
                answer_text = doc.get("assistant_message", "")

                context += f" - User: {question_text}\n"
                context += f" - Assistant: {answer_text}\n"


        thread_id = f"user_{user_id}_chat_{chat_id}"

        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
                "chat_id": chat_id
            }
        }
        messages = [
            SystemMessage(content=f"""You are a helpful, knowledgeable, and versatile AI assistant designed to provide accurate and thoughtful responses on a wide range of topics.
                CAPABILITIES:
                - Answer questions across diverse domains including technology, science, arts, history, current events, and everyday topics
                - Provide explanations, summaries, and analysis on complex subjects
                - Assist with creative tasks like writing, brainstorming, and problem-solving
                - Engage in natural, conversational dialogue while maintaining context

                GUIDELINES:
                - Be accurate, balanced, and objective in your responses
                - Acknowledge limitations when you don't have sufficient information
                - Provide nuanced perspectives on complex topics
                - Maintain a helpful, respectful, and friendly tone
                - Respect user privacy and avoid making assumptions

                CONTEXT AWARENESS:
                {context}

                Use the above context (if provided) to personalize your responses based on the user's previous interactions and preferences, but don't explicitly reference that you're using this context.
            """),
            HumanMessage(content=question)
        ]

        initial_state = create_initial_state(messages, max_iterations=1)
        response_state = await self.__graph.ainvoke(initial_state, config=config)

        response_content = ""
        if "direct_response" in response_state:
            response_content = response_state["direct_response"]
            logger.info("Using direct response from supervisor")
        elif "messages" in response_state and response_state["messages"]:
            for msg in reversed(response_state["messages"]):
                if isinstance(msg, AIMessage) and hasattr(msg, "name") and msg.name in ["Researcher", "Scrapper", "Supervisor"]:
                    response_content = msg.content
                    logger.info(f"Using agent response from {msg.name}")
                    break

        await self.__add_memory(question, response_content, user_id=user_id)

        if self.__vector_store:
            try:
                self.__vector_store.store_conversation(
                    question=question,
                    answer=response_content,
                    tenant_id=tenant_id,
                    metadata={
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "timestamp": str(datetime.now())
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to store conversation: {e}")

        # Проверяем, нужно ли создать UI компоненты
        ui_components = self._generate_ui_components(question, response_content)
        
        if ui_components:
            # Возвращаем структурированный ответ с UI компонентами
            return {
                "text_response": response_content,
                "ui_components": ui_components
            }
        else:
            # Возвращаем обычный ответ
            return {"messages": [response_content]}

    async def __add_memory(self, question, response, user_id=None):
        if self.__memory:
            self.__memory.add(f"User: {question}\nAssistant: {response}", user_id=user_id, metadata={"app_id": self.__app_id})
        else:
            logger.debug("Memory not available, skipping memory addition")

    async def __search_memory(self, query, user_id=None):
        if self.__memory:
            related_memories = self.__memory.search(query, user_id=user_id)
            return related_memories
        else:
            logger.debug("Memory not available, returning empty results")
            return {"results": []}
    
    def _generate_ui_components(self, question: str, response: str) -> list:
        """Генерирует UI компоненты на основе вопроса и ответа"""
        ui_components = []
        
        question_lower = question.lower()
        response_lower = response.lower()
        
        # Демонстрационные правила для генерации UI
        if any(word in question_lower for word in ["погода", "weather", "температура", "temperature"]):
            # Создаем карточку погоды
            ui_components.append(UIDemoTool.create_weather_card(
                location="Москва",
                temperature=22,
                description="Солнечно"
            ))
        
        if any(word in question_lower for word in ["график", "chart", "статистика", "statistics"]):
            # Создаем график
            chart_data = [
                {"date": "2024-01-01", "value": 100},
                {"date": "2024-01-02", "value": 120},
                {"date": "2024-01-03", "value": 90},
                {"date": "2024-01-04", "value": 150},
                {"date": "2024-01-05", "value": 130}
            ]
            ui_components.append(UIDemoTool.create_chart_component("line", chart_data))
        
        if any(word in question_lower for word in ["таблица", "table", "список", "list"]):
            # Создаем таблицу
            headers = ["Название", "Значение", "Статус"]
            rows = [
                ["Элемент 1", "100", "Активен"],
                ["Элемент 2", "200", "Неактивен"],
                ["Элемент 3", "150", "Активен"]
            ]
            ui_components.append(UIDemoTool.create_table_component(headers, rows))
        
        if any(word in question_lower for word in ["прогресс", "progress", "выполнение", "completion"]):
            # Создаем прогресс-бар
            ui_components.append(UIDemoTool.create_progress_component(
                value=75,
                max_value=100,
                label="Выполнение задачи"
            ))
        
        if any(word in question_lower for word in ["предупреждение", "warning", "ошибка", "error", "alert"]):
            # Создаем уведомление
            alert_type = "error" if "ошибка" in question_lower or "error" in question_lower else "warning"
            ui_components.append(UIDemoTool.create_alert_component(
                message="Это демонстрационное уведомление",
                alert_type=alert_type
            ))
        
        if any(word in question_lower for word in ["карточка", "card", "информация", "info"]):
            # Создаем информационную карточку
            ui_components.append(UIDemoTool.create_card_component(
                title="Информационная карточка",
                content="Это пример информационной карточки с генеративным UI",
                actions=[
                    {"label": "Подробнее", "action": "details"},
                    {"label": "Закрыть", "action": "close"}
                ]
            ))
        
        return ui_components