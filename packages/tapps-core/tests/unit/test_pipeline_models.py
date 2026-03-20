"""Tests for tapps_core.common.pipeline_models — pipeline stage definitions."""

from __future__ import annotations

from tapps_core.common.pipeline_models import STAGE_ORDER, STAGE_TOOLS, PipelineStage


class TestPipelineStage:
    """Verify PipelineStage enum members and ordering."""

    def test_has_five_stages(self) -> None:
        assert len(PipelineStage) == 5

    def test_stage_values(self) -> None:
        assert PipelineStage.DISCOVER == "discover"
        assert PipelineStage.RESEARCH == "research"
        assert PipelineStage.DEVELOP == "develop"
        assert PipelineStage.VALIDATE == "validate"
        assert PipelineStage.VERIFY == "verify"

    def test_is_str_enum(self) -> None:
        # StrEnum members are usable as plain strings
        assert f"stage={PipelineStage.DISCOVER}" == "stage=discover"


class TestStageOrder:
    """Verify STAGE_ORDER matches expected pipeline sequence."""

    def test_order_length(self) -> None:
        assert len(STAGE_ORDER) == 5

    def test_discover_is_first(self) -> None:
        assert STAGE_ORDER[0] is PipelineStage.DISCOVER

    def test_verify_is_last(self) -> None:
        assert STAGE_ORDER[-1] is PipelineStage.VERIFY

    def test_all_stages_present(self) -> None:
        assert set(STAGE_ORDER) == set(PipelineStage)


class TestStageTools:
    """Verify STAGE_TOOLS maps every stage to at least one tool."""

    def test_all_stages_have_tools(self) -> None:
        for stage in PipelineStage:
            assert stage in STAGE_TOOLS, f"Missing tools for {stage}"
            assert len(STAGE_TOOLS[stage]) > 0

    def test_session_start_in_discover(self) -> None:
        assert "tapps_session_start" in STAGE_TOOLS[PipelineStage.DISCOVER]

    def test_score_file_in_develop(self) -> None:
        assert "tapps_score_file" in STAGE_TOOLS[PipelineStage.DEVELOP]

    def test_checklist_in_verify(self) -> None:
        assert "tapps_checklist" in STAGE_TOOLS[PipelineStage.VERIFY]
