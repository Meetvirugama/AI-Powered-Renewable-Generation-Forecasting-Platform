from fastapi.testclient import TestClient

def test_health_check(client: TestClient):
    response = client.get('/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'healthy'
    assert 'timestamp' in data

def test_root_endpoint(client: TestClient):
    response = client.get('/')
    assert response.status_code == 200
    data = response.json()
    assert 'docs' in data

def test_get_plants(client: TestClient):
    response = client.get('/plants')
    assert response.status_code == 200
    data = response.json()
    assert data['total'] >= 4
    assert len(data['plants']) >= 4
    assert any(p['id'] == 'GJ_SOLAR_A' for p in data['plants'])

def test_get_single_plant(client: TestClient):
    response = client.get('/plants/GJ_SOLAR_A')
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 'GJ_SOLAR_A'
    assert data['type'] == 'solar'
    assert data['avc_mw'] == 50.0

def test_get_plant_not_found(client: TestClient):
    response = client.get('/plants/UNKNOWN_PLANT_XYZ')
    assert response.status_code == 404

def test_get_forecast(client: TestClient):
    response = client.get('/forecast?plant_id=GJ_SOLAR_A&date=2026-06-01')
    assert response.status_code == 200
    data = response.json()
    assert data['plant_id'] == 'GJ_SOLAR_A'
    assert len(data['blocks']) == 96
    first_block = data['blocks'][0]
    assert 'p10' in first_block
    assert 'p50' in first_block
    assert 'p90' in first_block

def test_post_dsm(client: TestClient):
    payload = {
        'plant_id': 'GJ_SOLAR_A',
        'date': '2026-06-01',
        'schedule_mw': [25.0] * 96,
        'rule_year': 2026,
        'freq_hz': 50.0,
        'ncd_inr': 450.0
    }
    response = client.post('/dsm', json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data['plant_id'] == 'GJ_SOLAR_A'
    assert 'total_expected_penalty_inr' in data
    assert len(data['blocks']) == 96

def test_post_optimize(client: TestClient):
    payload = {
        'plant_id': 'GJ_SOLAR_A',
        'date': '2026-06-01',
        'rule_year': 2026,
        'freq_hz': 50.0,
        'ncd_inr': 450.0
    }
    response = client.post('/optimize', json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data['optimised_schedule']) == 96
    assert 'savings_inr' in data
    assert 'savings_pct' in data
    assert 'action_cards' in data

def test_post_pooling(client: TestClient):
    payload = {
        'pool_id': 'GJ_POOL_1',
        'date': '2026-06-01',
        'rule_year': 2026,
        'freq_hz': 50.0,
        'ncd_inr': 450.0
    }
    response = client.post('/pooling', json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data['pool_id'] == 'GJ_POOL_1'
    assert 'pooled_total_inr' in data
    assert 'savings_pct' in data
    assert len(data['allocations']) >= 1

def test_get_dashboard(client: TestClient):
    response = client.get('/dashboard/GJ_SOLAR_A?date=2026-06-01')
    assert response.status_code == 200
    data = response.json()
    assert data['plant_id'] == 'GJ_SOLAR_A'
    assert 'forecast' in data
    assert 'dsm_summary' in data
    assert 'actions' in data
    assert 'briefing' in data

def test_post_rag_query(client: TestClient):
    payload = {
        'question': 'Why was block 45 penalized under CERC 2026 rules?',
        'plant_id': 'GJ_SOLAR_A',
        'block_no': 45
    }
    response = client.post('/rag/query', json=payload)
    assert response.status_code == 200
    data = response.json()
    assert 'answer' in data
    assert len(data['citations']) >= 1

def test_post_pipeline_run_missing_auth(client: TestClient):
    response = client.post('/pipeline/run', json={'target_date': '2026-06-01'})
    assert response.status_code == 401
    assert 'Invalid or missing API key' in response.json()['detail']

def test_post_pipeline_run_invalid_auth(client: TestClient):
    response = client.post(
        '/pipeline/run',
        json={'target_date': '2026-06-01'},
        headers={'x-api-key': 'WRONG_INVALID_KEY'}
    )
    assert response.status_code == 401
    assert 'Invalid or missing API key' in response.json()['detail']

def test_post_pipeline_run_valid_auth(client: TestClient):
    from backend.core.config import get_settings
    valid_key = get_settings().pipeline_api_key
    response = client.post(
        '/pipeline/run',
        json={'target_date': '2026-06-01'},
        headers={'x-api-key': valid_key}
    )
    assert response.status_code == 202
    data = response.json()
    assert data['status'] == 'accepted'
    assert 'run_id' in data

    # Test status endpoint with the created run_id (background task has finished in TestClient)
    run_id = data['run_id']
    status_resp = client.get(f'/pipeline/status/{run_id}')
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data['run_id'] == run_id
    assert status_data['status'] in ('accepted', 'running', 'success')

def test_get_pipeline_status_not_found(client: TestClient):
    response = client.get('/pipeline/status/NON_EXISTENT_RUN_UUID')
    assert response.status_code == 404

