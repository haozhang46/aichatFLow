from app.adapters.dify import DifyAdapter
from app.adapters.fastgpt import FastGptAdapter
from app.core.config import settings
from app.services.capability_service import CapabilityService
from app.services.executor import ExecutorService
from app.services.agent_registry_service import AgentRegistryService
from app.services.plan_record_service import PlanRecordService
from app.services.routes_repo import RouteRepository
from app.services.routing import RoutingService
from app.services.skill_executor_service import SkillExecutorService
from app.services.personal_skill_tree_service import PersonalSkillTreeService
from app.services.policy_engine import PolicyEngine
from app.services.trace_store import TraceStore
from app.services.metrics_service import MetricsService
from app.services.approval_store import ApprovalStore

route_repo = RouteRepository()
routing_service = RoutingService(route_repo)
executor_service = ExecutorService(
    {
        "fastgpt": FastGptAdapter(settings.fastgpt_base_url, settings.fastgpt_api_key),
        "dify": DifyAdapter(settings.dify_base_url, settings.dify_api_key),
    }
)
capability_service = CapabilityService()
agent_registry_service = AgentRegistryService()
plan_record_service = PlanRecordService()
metrics_service = MetricsService()
skill_executor_service = SkillExecutorService(capability_service, metrics_service)
personal_skill_tree_service = PersonalSkillTreeService()
policy_engine = PolicyEngine()
trace_store = TraceStore()
approval_store = ApprovalStore()
