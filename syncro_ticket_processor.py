import os
import csv
import json
import time
import logging
import schedule
import requests
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('syncro_processor.log'),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv()

# Configuration
SYNCRO_API_URL = 'https://cloudavize.syncromsp.com/api/v1'
SYNCRO_API_KEY = os.getenv('SYNCRO_API_KEY')
MAPPING_FILE = 'technician_mapping.json'
ASSIGNMENT_RESULTS_FILE = 'assignment_results.json'

def load_technician_mapping():
    """Load technician mapping from JSON file."""
    with open(MAPPING_FILE, 'r') as f:
        data = json.load(f)
    
    # Convert JSON structure to list of schedule entries
    mapping = []
    for tech_name, tech_info in data['technicians'].items():
        for schedule in tech_info['schedules']:
            for category in schedule['categories']:
                mapping.append({
                    'category': category,
                    'technician': tech_name,
                    'teams_mention': tech_info['teams_mention'],
                    'email': tech_info['email'],
                    'days': schedule['days'],
                    'start_time': schedule['start_time'],
                    'end_time': schedule['end_time']
                })
    return mapping, data['category_mapping']

def get_last_processed_timestamp():
    """Get the timestamp of the last processed ticket."""
    try:
        with open(LAST_PROCESSED_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        # If file doesn't exist, use current time
        current_time = datetime.now().isoformat()
        save_last_processed_timestamp(current_time)
        return current_time

def save_last_processed_timestamp(timestamp):
    """Save the timestamp of the last processed ticket."""
    with open(LAST_PROCESSED_FILE, 'w') as f:
        f.write(timestamp)

def get_new_tickets():
    """Get new tickets from Syncro API."""
    try:
        response = requests.get(
            f'{SYNCRO_API_URL}/tickets',
            headers={'Accept': 'application/json'},
            params={'api_key': SYNCRO_API_KEY}
        )
        response.raise_for_status()
        
        data = response.json()
        tickets = data.get('tickets', []) if isinstance(data, dict) else data
        
        if not isinstance(tickets, list):
            logging.error(f"Invalid tickets data format")
            return []
        
        # Get all unresolved tickets
        active_tickets = [t for t in tickets if isinstance(t, dict) 
                        and t.get('status') != 'Resolved']
        logging.info(f"Found {len(active_tickets)} active tickets")
        
        # Sort by created_at
        return sorted(active_tickets, key=lambda x: x.get('created_at', ''))
            
    except Exception as e:
        logging.error(f"Failed to get tickets: {e}")
        return []

def parse_time(time_str):
    """Parse time string to time object."""
    return datetime.strptime(time_str, '%H:%M').time()

def is_time_in_schedule(current_time, current_day, schedule_days, start_time, end_time):
    """Check if current time falls within the schedule."""
    # Convert schedule days to list (e.g., 'Mon-Fri' -> ['Mon', 'Fri'])
    schedule_range = schedule_days.split('-')
    days_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    start_idx = days_order.index(schedule_range[0])
    end_idx = days_order.index(schedule_range[1])
    
    # Handle wrap-around schedules (e.g., Sun-Thu)
    if end_idx < start_idx:
        schedule_days = days_order[start_idx:] + days_order[:end_idx+1]
    else:
        schedule_days = days_order[start_idx:end_idx+1]
    
    if current_day not in schedule_days:
        return False
        
    # Convert times to comparable format using real datetime
    current = parse_time(current_time)
    start = parse_time(start_time)
    end = parse_time(end_time)
    
    # Handle overnight shifts (e.g., 16:30-01:30)
    if end < start:
        return current >= start or current <= end
    else:
        return start <= current <= end

def map_syncro_category(category):
    """Map Syncro ticket categories to our internal categories."""
    category_mapping = {
        'Remote Support': 'Level 1',  # Default remote support to Level 1
        'Software': 'Software',
        'Account Management': 'Account Management'
    }
    return category_mapping.get(category, category)

def assign_technician(ticket, mapping_data):
    """Assign technician based on ticket category and time."""
    mappings, category_mapping = mapping_data
    
    # Get current time in the format used in the mapping
    current_time = datetime.now().strftime('%H:%M')
    current_day = datetime.now().strftime('%a')
    
    # First, check for time-based assignments (weekend/after-hours)
    for mapping in mappings:
        if mapping['category'] == 'All' and is_time_in_schedule(current_time, current_day, mapping['days'], mapping['start_time'], mapping['end_time']):
            return {
                'technician': mapping['technician'],
                'teams_mention': mapping['teams_mention'],
                'email': mapping['email']
            }
    
    # If not in special time periods, check regular category assignments
    ticket_category = ticket.get('problem_type', '')
    category = category_mapping.get(ticket_category, ticket_category)
    
    for mapping in mappings:
        if mapping['category'] == category and is_time_in_schedule(current_time, current_day, mapping['days'], mapping['start_time'], mapping['end_time']):
            return {
                'technician': mapping['technician'],
                'teams_mention': mapping['teams_mention'],
                'email': mapping['email']
            }
    
    return {'technician': 'Needs human input', 'teams_mention': None, 'email': None}

# TODO: Currently disabled - read-only mode
# def update_ticket_assignment(ticket_id, technician):
#     """Update ticket assignment in Syncro."""
#     headers = {
#         'Authorization': SYNCRO_API_KEY,
#         'Accept': 'application/json',
#         'Content-Type': 'application/json'
#     }
#     
#     data = {
#         'assigned_to': technician
#     }
#     
#     response = requests.put(
#         f'{SYNCRO_API_URL}/tickets/{ticket_id}',
#         headers=headers,
#         json=data
#     )
#     response.raise_for_status()

def save_assignment_result(ticket, assignment):
    """Save the ticket assignment result to a JSON file."""
    result = {
        'ticket_id': ticket.get('id'),
        'ticket_number': ticket.get('number'),
        'subject': ticket.get('subject'),
        'category': ticket.get('problem_type'),
        'assigned_to': assignment['technician'],
        'teams_mention': assignment['teams_mention'],
        'timestamp': datetime.now().isoformat(),
        'description': ticket.get('description'),
        'status': ticket.get('status'),
        'priority': ticket.get('priority')
    }
    
    try:
        # Load existing results
        if os.path.exists(ASSIGNMENT_RESULTS_FILE):
            with open(ASSIGNMENT_RESULTS_FILE, 'r') as f:
                results = json.load(f)
        else:
            results = []
        
        # Add new result
        results.append(result)
        
        # Save back to file
        with open(ASSIGNMENT_RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=2)
            
    except Exception as e:
        print(f"Error saving assignment result: {str(e)}")

def process_tickets():
    """Main function to process new tickets."""
    try:
        # Load technician mapping
        mapping = load_technician_mapping()
        if not mapping:
            logging.error("No technician mappings found")
            return
        
        # Get new unassigned tickets
        unassigned_tickets = get_new_tickets()
        if not unassigned_tickets:
            return
        
        # Process each ticket
        for ticket in unassigned_tickets:
            try:
                # Assign technician
                assignment = assign_technician(ticket, mapping)
                if not assignment:
                    continue
                
                # TODO: Update ticket in Syncro (currently disabled - read-only mode)
                # if assignment['technician'] != 'Needs human input':
                #     update_ticket_assignment(ticket['id'], assignment['technician'])
                
                # Save assignment result
                save_assignment_result(ticket, assignment)
                logging.info(f"Processed ticket #{ticket.get('number')}: Assigned to {assignment['technician']}")
                    
            except Exception as e:
                logging.error(f"Error processing ticket {ticket.get('id', 'Unknown')}: {str(e)}")
                
    except Exception as e:
        logging.error(f"Error in process_tickets: {str(e)}")

def main():
    """Main entry point."""
    logging.info("Starting Syncro ticket processor")
    
    # Schedule the job to run every 5 minutes
    schedule.every(5).minutes.do(process_tickets)
    
    # Run immediately on startup
    process_tickets()
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
