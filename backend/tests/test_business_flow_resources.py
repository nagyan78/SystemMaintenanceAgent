from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.main import create_app
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.review_batch_repo import ReviewBatchRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.schemas.taxonomy import TaxonomyNodeRecord


def _settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path/'app.db'}", upload_dir=tmp_path/'uploads',
                    report_dir=tmp_path/'reports', export_dir=tmp_path/'exports',
                    deepseek_api_key='', dashscope_api_key='', enable_legacy_manual_review_api=True)


def _seed(settings):
    init_db(settings)
    with connect(settings) as c:
        c.execute("INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'taxonomy.xlsx','taxonomy.xlsx')")
    version_id = VersionRepository(settings).create_version(file_id=1, version_no='v1.0')
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=[
        TaxonomyNodeRecord(category_id=1, category_name='根', parent_id=None, level=1, path_ids='1', path_names='根', is_leaf=0),
        TaxonomyNodeRecord(category_id=2, category_name='其他', parent_id=1, level=2, path_ids='1,2', path_names='根 > 其他', is_leaf=1),
    ])
    issue_id = DiagnosisRepository(settings).create_issue(version_id=version_id, issue=DiagnosisIssueRecord(
        issue_type='ambiguous_name', node_id=2, node_name='其他', description='名称模糊',
        reason='规则命中', risk_level='low', confidence=1,
    ))
    batch_id='review_resource'
    SuggestionRepository(settings).create_suggestion(review_batch_id=batch_id, suggestion=AdjustmentSuggestion(
        issue_id=issue_id, version_id=version_id, action_type='rename_node', target_node_id=2,
        new_name='其他产品', action_payload={'new_name':'其他产品'}, reason='模糊',
        suggestion='重命名', risk_level='low', confidence=1, need_confirm=True,
    ))
    task_id=TaskRepository(settings).create_workflow_task(file_id=1, workflow_id='wf_resource', thread_id='thread_resource')
    TaskRepository(settings).update_task(task_id=task_id,status='waiting_review',current_step='review_pending',progress=80,version_id=version_id)
    ReviewBatchRepository(settings).create(batch_id=batch_id,file_id=1,version_id=version_id,task_id=task_id,workflow_id='wf_resource')
    return version_id,batch_id,task_id


def test_resource_centers_and_report_gate(tmp_path):
    settings=_settings(tmp_path); version_id,batch_id,task_id=_seed(settings); client=TestClient(create_app(settings))
    workflows=client.get('/api/workflows').json(); reviews=client.get('/api/reviews').json()
    assert workflows[0]['id']==task_id and workflows[0]['review_batch_id']==batch_id
    assert reviews[0]['id']==batch_id and reviews[0]['status']=='in_review'
    assert client.get(f'/api/reports/{version_id}/preview?report_type=final').status_code==409
    assert client.get(f'/api/reports/{version_id}/preview?report_type=draft').status_code==200
    quality=client.get(f'/api/versions/{version_id}/quality').json()
    assert quality['after_issue_count']==1
    assert client.post(f'/api/reviews/{batch_id}/execute',json={'operator':'tester'}).status_code==400


def test_review_execution_creates_snapshot_new_version_and_final_report(tmp_path):
    settings = _settings(tmp_path)
    version_id, batch_id, task_id = _seed(settings)
    client = TestClient(create_app(settings))
    suggestion_id = client.get(f'/api/reviews/{batch_id}').json()['suggestions'][0]['id']

    decision = client.post(
        f'/api/reviews/{batch_id}/decision',
        json={
            'decision': 'approve',
            'approved_suggestion_ids': [suggestion_id],
            'operator': 'tester',
        },
    )
    assert decision.status_code == 200
    assert decision.json()['batch']['status'] == 'reviewed'
    assert decision.json()['batch']['execution_status'] == 'missing'
    preview = client.post(f'/api/reviews/{batch_id}/execution-preview', json={})
    assert preview.status_code == 200 and preview.json()['valid'] is True

    execution = client.post(
        f'/api/reviews/{batch_id}/execute', json={'operator': 'tester'}
    )
    assert execution.status_code == 200
    result = execution.json()
    new_version_id = result['new_version_id']
    versions = client.get('/api/versions?file_id=1').json()
    base_version = next(item for item in versions if item['id'] == version_id)
    new_version = next(item for item in versions if item['id'] == new_version_id)
    assert base_version['snapshot_path']
    assert new_version['parent_version_id'] == version_id
    assert new_version['verification_status'] in {'passed', 'partial'}
    assert client.get(
        f'/api/reports/{new_version_id}/preview?report_type=final'
    ).status_code == 200
    assert client.get(f'/api/workflows/{task_id}').json()['status'] == 'completed'
    batch = client.get(f'/api/reviews/{batch_id}').json()['batch']
    assert batch['execution_status'] == 'executed'
    assert batch['new_version_id'] == new_version_id


def test_all_rejected_batch_refuses_empty_preview_and_execution(tmp_path):
    settings = _settings(tmp_path)
    version_id, batch_id, task_id = _seed(settings)
    client = TestClient(create_app(settings))
    suggestion_id = client.get(f'/api/reviews/{batch_id}').json()['suggestions'][0]['id']

    decision = client.post(
        f'/api/reviews/{batch_id}/decision',
        json={
            'decision': 'reject',
            'rejected_suggestion_ids': [suggestion_id],
            'operator': 'tester',
            'reject_reason': '人工确认不准确',
        },
    )
    assert decision.status_code == 200
    assert decision.json()['batch']['execution_status'] == 'missing'
    assert decision.json()['completion']['reason'] == 'no_executable_actions'
    assert client.get(f'/api/workflows/{task_id}').json()['status'] == 'completed'
    assert client.get(f'/api/reports/{version_id}/preview?report_type=final').status_code == 200

    execution = client.post(
        f'/api/reviews/{batch_id}/execute', json={'operator': 'tester'}
    )
    assert client.post(f'/api/reviews/{batch_id}/execution-preview', json={}).status_code == 400
    assert execution.status_code == 400


def test_empty_diagnosis_batch_is_reviewable_and_can_finish(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'clean.xlsx','clean.xlsx')"
        )
    version_id = VersionRepository(settings).create_version(file_id=1, version_no='v1.0')
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[TaxonomyNodeRecord(
            category_id=1, category_name='根节点', parent_id=None, level=1,
            path_ids='1', path_names='根节点', is_leaf=1,
        )],
    )
    task_id = TaskRepository(settings).create_workflow_task(
        file_id=1, workflow_id='wf_empty', thread_id='thread_empty'
    )
    TaskRepository(settings).update_task(
        task_id=task_id, status='waiting_review', current_step='review_pending',
        progress=80, version_id=version_id,
    )
    batch_id = 'review_empty'
    batches = ReviewBatchRepository(settings)
    batches.create(
        batch_id=batch_id, file_id=1, version_id=version_id,
        task_id=task_id, workflow_id='wf_empty',
    )
    batches.refresh_status(batch_id)
    client = TestClient(create_app(settings))

    review = client.get(f'/api/reviews/{batch_id}')
    assert review.status_code == 200
    assert review.json()['suggestion_count'] == 0
    assert review.json()['batch']['status'] == 'reviewed'
    assert review.json()['batch']['execution_status'] == 'missing'
    assert client.get(
        f'/api/reports/{version_id}/preview?report_type=final'
    ).status_code == 409

    execution = client.post(
        f'/api/reviews/{batch_id}/execute', json={'operator': 'tester'}
    )
    assert client.post(f'/api/reviews/{batch_id}/execution-preview', json={}).status_code == 400
    assert execution.status_code == 400


def test_execution_failure_records_evidence_and_creates_no_version(tmp_path, monkeypatch):
    from backend.app.services.action_service import ActionService

    settings = _settings(tmp_path)
    version_id, batch_id, _ = _seed(settings)
    client = TestClient(create_app(settings))
    suggestion_id = client.get(f'/api/reviews/{batch_id}').json()['suggestions'][0]['id']
    assert client.post(f'/api/reviews/{batch_id}/decision', json={
        'decision':'approve','approved_suggestion_ids':[suggestion_id],
        'operator':'tester',
    }).status_code == 200
    assert client.post(f'/api/reviews/{batch_id}/execution-preview', json={}).status_code == 200

    def fail_execution(*args, **kwargs):
        raise ValueError('simulated transactional failure')

    monkeypatch.setattr(ActionService, 'execute_suggestion_records', fail_execution)
    response = client.post(f'/api/reviews/{batch_id}/execute', json={'operator':'tester'})
    assert response.status_code == 400
    assert [item['id'] for item in VersionRepository(settings).list_versions(file_id=1)] == [version_id]
    with connect(settings) as connection:
        record = connection.execute(
            "SELECT status,target_version_id,error_code,error_message FROM version_execution_record WHERE review_batch_id=?",
            (batch_id,),
        ).fetchone()
    assert tuple(record) == ('failed', None, 'ValueError', 'simulated transactional failure')
    assert client.get(f'/api/reviews/{batch_id}').json()['batch']['execution_status'] == 'failed'
