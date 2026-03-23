from app.adapters.dify import DifyAdapter
from app.adapters.fastgpt import FastGptAdapter
from app.core.config import settings
from app.memory.plan_store import PlanStore
from app.observability.otie_trace_service import OtieTraceService
from app.planner.intent_service import IntentService
from app.planner.planner_service import PlannerService
from app.policy.runtime_policy import RuntimePolicyService
from app.runtime.deepagent_adapter import DeepAgentRuntimeAdapter
from app.runtime.loop import OtieRuntime
from app.runtime.platform_file_adapter import PlatformFileAdapter
from app.runtime.platform_tool_adapter import PlatformToolAdapter
from app.runtime.platform_trace_adapter import PlatformTraceAdapter
from app.services.capability_service import CapabilityService
from app.services.executor import ExecutorService
from app.services.file_acl_service import FileAclService
from app.services.file_service import FileService
from app.services.agent_registry_service import AgentRegistryService
from app.services.tool_definition_registry_service import ToolDefinitionRegistryService
from app.services.plan_record_service import PlanRecordService
from app.services.routes_repo import RouteRepository
from app.services.routing import RoutingService
from app.services.skill_executor_service import SkillExecutorService
from app.services.tool_executor_adapter_service import ToolExecutorAdapterService
from app.services.personal_skill_tree_service import PersonalSkillTreeService
from app.services.platform_trace_service import PlatformTraceService
from app.services.policy_engine import PolicyEngine
from app.services.rag_service import RagService
from app.services.trace_store import TraceStore
from app.services.metrics_service import MetricsService
from app.services.approval_store import ApprovalStore
from app.services.tool_policy_service import ToolPolicyService
from app.tools.builtin import (
    ExecuteSkillTool,
    FileDeleteTool,
    FileListTool,
    FileMkdirTool,
    FilePatchTool,
    FileReadTool,
    FileWriteTool,
    FindSkillsTool,
    InstallSkillTool,
    RetrievalTool,
    WeatherTool,
    WebFetchTool,
)
from app.tools.registry import ToolRegistry

route_repo = RouteRepository()
routing_service = RoutingService(route_repo)
executor_service = ExecutorService(
    {
        "fastgpt": FastGptAdapter(settings.fastgpt_base_url, settings.fastgpt_api_key),
        "dify": DifyAdapter(settings.dify_base_url, settings.dify_api_key),
    }
)
capability_service = CapabilityService()
file_acl_service = FileAclService()
file_service = FileService()
agent_registry_service = AgentRegistryService()
tool_definition_registry_service = ToolDefinitionRegistryService()
plan_record_service = PlanRecordService()
metrics_service = MetricsService()
skill_executor_service = SkillExecutorService(capability_service, metrics_service)
personal_skill_tree_service = PersonalSkillTreeService()
rag_service = RagService()
policy_engine = PolicyEngine()
trace_store = TraceStore()
platform_trace_service = PlatformTraceService(trace_store)
approval_store = ApprovalStore()
plan_store = PlanStore()
otie_trace_service = OtieTraceService(trace_store, plan_store)
otie_intent_service = IntentService()
otie_planner = PlannerService(capability_service, plan_store)
builtin_tools = [
    FindSkillsTool(capability_service),
    InstallSkillTool(capability_service),
    ExecuteSkillTool(skill_executor_service),
    WeatherTool(),
    RetrievalTool(rag_service),
    WebFetchTool(),
    FileListTool(file_service, file_acl_service, platform_trace_service),
    FileReadTool(file_service, file_acl_service, platform_trace_service),
    FileWriteTool(file_service, file_acl_service, platform_trace_service),
    FileDeleteTool(file_service, file_acl_service, platform_trace_service),
    FileMkdirTool(file_service, file_acl_service, platform_trace_service),
    FilePatchTool(file_service, file_acl_service, platform_trace_service),
]
tool_registry = ToolRegistry(builtin_tools)
tool_executor_adapter_service = ToolExecutorAdapterService(tool_registry)
tool_registry = ToolRegistry(
    builtin_tools,
    definition_registry=tool_definition_registry_service,
    executor_adapter=tool_executor_adapter_service,
    platform_trace_service=platform_trace_service,
)
platform_tool_adapter = PlatformToolAdapter(tool_registry)
platform_file_adapter = PlatformFileAdapter(platform_tool_adapter)
platform_trace_adapter = PlatformTraceAdapter(platform_trace_service)
deepagent_runtime_adapter = DeepAgentRuntimeAdapter(
    platform_tool_adapter,
    platform_file_adapter,
    platform_trace_adapter,
)
runtime_policy_service = RuntimePolicyService(policy_engine)
tool_policy_service = ToolPolicyService(policy_engine)
otie_runtime = OtieRuntime(tool_registry, runtime_policy_service, otie_trace_service, platform_trace_service)
