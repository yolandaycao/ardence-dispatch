import os
import json
import pytest
import responses
from datetime import datetime
from syncro_ticket_processor import (
    get_new_tickets,
    assign_technician,
    save_assignment_result,
    process_tickets,
    load_technician_mapping,
    SYNCRO_API_URL,
    SYNCRO_API_KEY,
    MAPPING_FILE,
    ASSIGNMENT_RESULTS_FILE
)

@pytest.fixture
def sample_tickets():
    """Sample ticket data."""
    test_data_path = os.path.join(os.path.dirname(__file__), 'test_data/sample_tickets_unassigned.json')
    with open(test_data_path, 'r') as f:
        return json.load(f)

@pytest.fixture
def sample_mapping():
    """Sample technician mapping data."""
    with open('technician_mapping.json', 'r') as f:
        return json.load(f)

@pytest.fixture
def clean_assignment_results():
    # Clean up any existing results file
    if os.path.exists(ASSIGNMENT_RESULTS_FILE):
        os.remove(ASSIGNMENT_RESULTS_FILE)
    yield
    if os.path.exists(ASSIGNMENT_RESULTS_FILE):
        os.remove(ASSIGNMENT_RESULTS_FILE)

@responses.activate
def test_get_new_tickets(sample_tickets):
    # Mock Syncro API response
    responses.add(
        responses.GET,
        f"{SYNCRO_API_URL}/tickets",
        json=sample_tickets,
        status=200
    )
    
    # Get unassigned tickets
    tickets = get_new_tickets()
    
    # Should get unassigned and unresolved tickets
    unassigned_tickets = [t for t in tickets if t.get('user_id') is None]
    assert len(unassigned_tickets) == 1  # One unassigned ticket in sample data

    # Verify we can process Remote Support tickets
    remote_support_tickets = [t for t in tickets if t.get('problem_type') == 'Remote Support']
    assert len(remote_support_tickets) == 1
    
    # Verify ticket details
    ticket = remote_support_tickets[0]
    assert ticket['subject'] == 'Cannot Access Email'
    assert ticket['status'] == 'New'
    assert ticket['problem_type'] == 'Remote Support'

def test_assign_technician(sample_mapping, monkeypatch):
    # Base ticket template
    ticket = {
        'id': 95105275,
        'subject': 'Test Ticket',
        'status': 'New',
        'problem_type': 'Remote Support'
    }
    
    # Mock datetime for testing
    class MockDateTime:
        @classmethod
        def now(cls):
            return cls.mock_now
        
        @classmethod
        def strptime(cls, date_string, format):
            return datetime.strptime(date_string, format)
    
    monkeypatch.setattr('syncro_ticket_processor.datetime', MockDateTime)
    mapping = load_technician_mapping()
    
    # Test Matrix: Time Slots
    time_slots = [
        # Business Hours
        {'time': datetime(2025, 5, 22, 10, 0), 'day': 'Thu', 'desc': 'Business Hours'},  # Thu 10 AM
        {'time': datetime(2025, 5, 22, 16, 0), 'day': 'Thu', 'desc': 'Late Business Hours'},  # Thu 4 PM
        # After Hours
        {'time': datetime(2025, 5, 22, 17, 0), 'day': 'Thu', 'desc': 'Early After Hours'},  # Thu 5 PM
        {'time': datetime(2025, 5, 22, 20, 0), 'day': 'Thu', 'desc': 'After Hours'},  # Thu 8 PM
        {'time': datetime(2025, 5, 22, 1, 0), 'day': 'Thu', 'desc': 'Overnight'},  # Thu 1 AM
        # Weekend Hours
        {'time': datetime(2025, 5, 24, 9, 0), 'day': 'Sat', 'desc': 'Weekend Morning'},  # Sat 9 AM
        {'time': datetime(2025, 5, 24, 14, 0), 'day': 'Sat', 'desc': 'Weekend Afternoon'},  # Sat 2 PM
        {'time': datetime(2025, 5, 24, 18, 30), 'day': 'Sat', 'desc': 'Weekend Evening'},  # Sat 6:30 PM
        # Edge Cases
        {'time': datetime(2025, 5, 23, 16, 29), 'day': 'Fri', 'desc': 'Just Before After Hours'},  # Fri 4:29 PM
        {'time': datetime(2025, 5, 23, 16, 31), 'day': 'Fri', 'desc': 'Just After After Hours Start'},  # Fri 4:31 PM
    ]
    
    # Test Matrix: Categories
    categories = [
        {'type': 'Remote Support', 'business_hours_tech': ['Michael Barbin', 'Jomaree Lawsin']},
        {'type': 'Software', 'business_hours_tech': ['Carl Tamayo']},
        {'type': 'Account Management', 'business_hours_tech': ['Jomaree Lawsin']},
        {'type': 'Unknown', 'business_hours_tech': ['Needs human input']}
    ]
    
    # Run all combinations
    for time_slot in time_slots:
        MockDateTime.mock_now = time_slot['time']
        
        for category in categories:
            ticket['problem_type'] = category['type']
            assignment = assign_technician(ticket, mapping)
            
            # Business Hours Routing (Mon-Fri 8 AM - 5 PM)
            if (time_slot['day'] in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'] and
                time_slot['time'].hour >= 8 and time_slot['time'].hour < 16):
                if category['type'] == 'Unknown':
                    assert assignment['technician'] == 'Needs human input', \
                        f"Failed: {category['type']} during {time_slot['desc']}"
                    assert assignment['email'] is None
                else:
                    assert assignment['technician'] in category['business_hours_tech'], \
                        f"Failed: {category['type']} during {time_slot['desc']}"
                    assert assignment['email'].endswith('@cloudavize.com')
            
            # After Hours Routing (Sun-Thu 4:30 PM - 1:30 AM)
            elif ((time_slot['day'] in ['Sun', 'Mon', 'Tue', 'Wed', 'Thu'] and
                  time_slot['time'].hour >= 16 and time_slot['time'].minute >= 30) or
                 (time_slot['day'] in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'] and
                  time_slot['time'].hour < 1 and time_slot['time'].minute <= 30)):
                assert assignment['technician'] == 'Jorenzo Lucero', \
                    f"Failed: {category['type']} during {time_slot['desc']}"
                assert assignment['email'] == 'jlucero@cloudavize.com'
            
            # Weekend Hours Routing (Fri-Mon 8 AM - 7 PM)
            elif (time_slot['day'] in ['Fri', 'Sat', 'Sun', 'Mon'] and
                  time_slot['time'].hour >= 8 and time_slot['time'].hour < 19):
                assert assignment['technician'] == 'Carl Lim', \
                    f"Failed: {category['type']} during {time_slot['desc']}"
                assert assignment['email'] == 'clim@cloudavize.com'

def test_save_assignment_result(clean_assignment_results):
    ticket = {
        'id': 1,
        'number': 'T1001',
        'subject': 'Test ticket',
        'problem_type': 'Hardware',
        'description': 'Test description',
        'status': 'New',
        'priority': 'High'
    }
    
    assignment = {
        'technician': 'John Smith',
        'teams_mention': '@john.smith'
    }
    
    # Save first assignment
    save_assignment_result(ticket, assignment)
    
    # Verify file exists and content is correct
    assert os.path.exists(ASSIGNMENT_RESULTS_FILE)
    with open(ASSIGNMENT_RESULTS_FILE, 'r') as f:
        results = json.load(f)
    
    assert len(results) == 1
    assert results[0]['ticket_id'] == 1
    assert results[0]['assigned_to'] == 'John Smith'
    
    # Save another assignment
    ticket['id'] = 2
    ticket['number'] = 'T1002'
    save_assignment_result(ticket, assignment)
    
    # Verify both assignments are saved
    with open(ASSIGNMENT_RESULTS_FILE, 'r') as f:
        results = json.load(f)
    
    assert len(results) == 2
    assert results[1]['ticket_id'] == 2

@responses.activate
def test_process_tickets_integration(sample_tickets, sample_mapping, clean_assignment_results):
    # Mock Syncro API response
    responses.add(
        responses.GET,
        f"{SYNCRO_API_URL}/tickets",
        json=sample_tickets,
        status=200
    )
    
    # Process tickets
    process_tickets()
    
    # Verify assignments were saved
    assert os.path.exists(ASSIGNMENT_RESULTS_FILE)
    with open(ASSIGNMENT_RESULTS_FILE, 'r') as f:
        results = json.load(f)
    
    # Verify we can process tickets
    assert len(results) > 0
    
    # Verify the assignments have required fields
    for result in results:
        assert 'ticket_number' in result
        assert 'category' in result
        assert 'assigned_to' in result
        assert 'subject' in result
