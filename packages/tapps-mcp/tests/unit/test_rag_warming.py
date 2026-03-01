"""Unit tests for expert RAG warming."""

from tapps_mcp.experts.rag_warming import tech_stack_to_expert_domains
from tapps_mcp.project.models import TechStack


class TestTechStackToExpertDomains:
    def test_empty_tech_stack_returns_defaults(self):
        ts = TechStack()
        domains = tech_stack_to_expert_domains(ts)
        assert "software-architecture" in domains

    def test_python_adds_code_quality(self):
        ts = TechStack(languages=["python"])
        domains = tech_stack_to_expert_domains(ts)
        assert "software-architecture" in domains
        assert "code-quality-analysis" in domains

    def test_pytest_maps_to_testing_strategies(self):
        ts = TechStack(frameworks=["pytest"])
        domains = tech_stack_to_expert_domains(ts)
        assert "testing-strategies" in domains

    def test_fastapi_maps_to_api_design(self):
        ts = TechStack(frameworks=["fastapi"])
        domains = tech_stack_to_expert_domains(ts)
        assert "api-design-integration" in domains

    def test_docker_maps_to_cloud_and_devworkflow(self):
        ts = TechStack(libraries=["docker"])
        domains = tech_stack_to_expert_domains(ts)
        assert "cloud-infrastructure" in domains
        assert "development-workflow" in domains

    def test_domain_api_maps_to_api_design(self):
        ts = TechStack(domains=["api"])
        domains = tech_stack_to_expert_domains(ts)
        assert "api-design-integration" in domains

    def test_deduplication(self):
        ts = TechStack(
            frameworks=["fastapi", "flask"],
            domains=["api"],
        )
        domains = tech_stack_to_expert_domains(ts)
        # api-design-integration should appear once
        assert domains.count("api-design-integration") == 1
