from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.maintenance_cleanup_service import MaintenanceCleanupService
from backend.app.services.suggestion_consistency_service import SuggestionConsistencyService


def settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path/'app.db'}", upload_dir=tmp_path/'uploads',
                    export_dir=tmp_path/'exports', report_dir=tmp_path/'reports')


def seed_issue(tmp_path: Path):
    cfg = settings(tmp_path); init_db(cfg)
    upload = tmp_path/'uploads'/'source.xlsx'; upload.parent.mkdir(); upload.write_bytes(b'x')
    with connect(cfg) as c: c.execute("INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'source.xlsx',?)", (str(upload),))
    version = VersionRepository(cfg).create_version(file_id=1, version_no='v1.0')
    TaxonomyRepository(cfg).bulk_insert_nodes(version_id=version, nodes=[
        TaxonomyNodeRecord(category_id=1, category_name='仓储货物堆放架', parent_id=None, level=1, path_ids='1', path_names='仓储货物堆放架'),
        TaxonomyNodeRecord(category_id=7079, category_name='金属货架', parent_id=1, level=2, path_ids='1,7079', path_names='仓储货物堆放架 > 金属货架'),
    ])
    issue = DiagnosisRepository(cfg).create_issue(version_id=version, issue=DiagnosisIssueRecord(
        issue_type='naming_nonstandard', node_id=7079, node_name='金属货架', description='名称不规范',
        reason='缺少用途限定', risk_level='medium', confidence=1, path='仓储货物堆放架 > 金属货架'))
    return cfg, version, issue


def test_consistency_rejects_parent_target_and_name_plus_category(tmp_path):
    cfg, version, issue = seed_issue(tmp_path); service = SuggestionConsistencyService(cfg)
    wrong = AdjustmentSuggestion(issue_id=issue, version_id=version, action_type='rename_node', target_node_id=1,
        old_name='仓储货物堆放架', new_name='仓储货物堆放架分类', action_payload={'new_name':'仓储货物堆放架分类'},
        reason='x', suggestion='x', risk_level='medium', confidence=1)
    result = service.check(wrong, normalize_new=True)
    assert result.downgraded and result.suggestion.action_type == 'review_only'
    assert '问题主体节点' in (result.reason or '')
    fallback = wrong.model_copy(update={'target_node_id':7079, 'old_name':'金属货架', 'new_name':'金属货架分类', 'action_payload':{'new_name':'金属货架分类'}})
    result = service.check(fallback, normalize_new=True)
    assert result.downgraded and '原名称+分类' in (result.reason or '')


def test_consistency_accepts_explicit_semantic_rename(tmp_path):
    cfg, version, issue = seed_issue(tmp_path)
    suggestion = AdjustmentSuggestion(issue_id=issue, version_id=version, action_type='rename_node', target_node_id=7079,
        old_name='金属货架', new_name='仓储用金属货架', action_payload={'new_name':'仓储用金属货架'},
        reason='用途限定', suggestion='规范命名', risk_level='medium', confidence=1)
    result = SuggestionConsistencyService(cfg).check(suggestion, normalize_new=True)
    assert result.valid and result.executable and not result.downgraded


def test_cleanup_preview_blocks_running_and_deletes_failed_transactionally(tmp_path):
    cfg = settings(tmp_path); init_db(cfg)
    upload = tmp_path/'uploads'/'source.xlsx'; upload.parent.mkdir(); upload.write_bytes(b'x')
    with connect(cfg) as c:
        c.execute("INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'source.xlsx',?)", (str(upload),))
        c.execute("INSERT INTO task_record(id,file_id,task_type,status,progress) VALUES('running',1,'taxonomy_workflow','running',20)")
        c.execute("INSERT INTO task_record(id,file_id,task_type,status,progress) VALUES('failed',1,'taxonomy_workflow','failed',0)")
    service = MaintenanceCleanupService(cfg)
    blocked = service.preview({'workflow_ids':['running']})
    assert blocked['blocking_reasons']
    preview = service.preview({'workflow_ids':['failed']})
    assert preview['task_count'] == 1 and not preview['blocking_reasons']
    result = service.execute(preview['cleanup_preview_id'], 'CONFIRM')
    assert result['deleted']['task_record'] == 1
    assert Path(result['database_backup_path']).is_file()
    with connect(cfg) as c:
        assert c.execute("SELECT COUNT(*) FROM task_record WHERE id='failed'").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM task_record WHERE id='running'").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM maintenance_cleanup_audit").fetchone()[0] == 1


def test_force_cleanup_cancels_and_deletes_running_task_in_one_operation(tmp_path):
    cfg = settings(tmp_path); init_db(cfg)
    upload = tmp_path/'uploads'/'source.xlsx'; upload.parent.mkdir(); upload.write_bytes(b'x')
    with connect(cfg) as c:
        c.execute("INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'source.xlsx',?)", (str(upload),))
        c.execute("INSERT INTO task_record(id,file_id,task_type,status,progress) VALUES('running',1,'taxonomy_workflow','running',20)")
    service = MaintenanceCleanupService(cfg)
    preview = service.preview({'workflow_ids':['running'], 'force_cancel_running':True})
    assert not preview['blocking_reasons']
    result = service.execute(preview['cleanup_preview_id'], 'CONFIRM')
    assert result['deleted']['task_record'] == 1
    with connect(cfg) as c:
        assert c.execute("SELECT COUNT(*) FROM task_record WHERE id='running'").fetchone()[0] == 0


def test_cleanup_rejects_preview_when_scope_changes(tmp_path):
    cfg = settings(tmp_path); init_db(cfg)
    with connect(cfg) as c:
        c.execute("INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'source.xlsx','source.xlsx')")
        c.execute("INSERT INTO task_record(id,file_id,task_type,status,progress) VALUES('failed',1,'diagnosis','failed',0)")
    service = MaintenanceCleanupService(cfg)
    preview = service.preview({'file_ids':[1], 'force_cancel_running':True})
    with connect(cfg) as c:
        c.execute("INSERT INTO task_record(id,file_id,task_type,status,progress) VALUES('late',1,'diagnosis','failed',0)")
    with pytest.raises(ValueError, match='旧预览失效'):
        service.execute(preview['cleanup_preview_id'], 'CONFIRM')
