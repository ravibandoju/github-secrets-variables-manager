import os
import argparse
import logging
from github import Github
import pandas as pd
from datetime import datetime
import requests

logging.basicConfig(level=logging.INFO)

def get_selected_repositories(item):
    if item.visibility == 'selected':
        return [r.name for r in item.selected_repositories]
    return None

def get_org_variable_value(token, org_name, var_name):
    """
    Fetch the value of a variable or secret using the GitHub API directly.
    """
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    url = f'https://api.github.com/orgs/{org_name}/actions/variables/{var_name}'
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get('value')
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch value for variable '{var_name}' in org '{org_name}': {e}")
        return None

def get_items_org(item, item_type, fetch_values=False, token=None, org_name=None):
    """
    Generic function to get secrets or variables from an organization.
    """
    items = []
    try:
        for i in getattr(item, f'get_{item_type}')():
            item_data = {
                'Name': i.name,
                'Visibility': getattr(i, 'visibility', None),
                'SelectedRepositories': get_selected_repositories(i)
            }
            if fetch_values and item_type == 'variables' and token and org_name:
                item_data['Value'] = get_org_variable_value(token, org_name, i.name)
            items.append(item_data)
    except Exception as e:
        logging.error(f"Failed to get {item_type} from organization: {e}")
    return items

def get_items_repo(item, item_type, fetch_values=False):
    """
    Generic function to get secrets or variables from a repository.
    """
    items = []
    try:
        for i in getattr(item, f'get_{item_type}')():
            item_data = {
                'Repository': item.name,
                'Name': i.name,
            }
            if fetch_values and item_type == 'variables':
                item_data['Value'] = i.value
            items.append(item_data)
    except Exception as e:
        logging.error(f"Failed to get {item_type} from repository {item.name}: {e}")
    return items

def get_env_items_repo(repo, item_type, fetch_values=False):
    """
    Get environment variables from a repository.
    """
    items = []
    try:
        get_item_type = f'get_{item_type}'
        environments = repo.get_environments()
        for env in environments:
            for i in getattr(env, get_item_type)():
                item_data = {
                    'Repository': repo.name,
                    'Environment': env.name,
                    'Name': i.name
                }
                if fetch_values and item_type == 'variables':
                    item_data['Value'] = i.value
                items.append(item_data)
    except Exception as e:
        logging.error(f"Failed to fetch environment {item_type} for repo {repo.name}: {e}")
    return items

def export_to_excel(data, filename, sheet_name):
    df = pd.DataFrame(data)
    try:
        with pd.ExcelWriter(filename, engine='openpyxl', mode='a' if os.path.exists(filename) else 'w') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    except PermissionError:
        logging.error(f"Permission denied: could not write to {filename}, please close the file if it is open")

def get_repo_ids(org, repo_names):
    """
    Convert a list of repository names to a list of repository IDs.
    """
    repo_ids = []
    for repo_name in repo_names:
        try:
            repo = org.get_repo(repo_name.strip())
            repo_ids.append(repo)
        except Exception as e:
            logging.error(f"Failed to get repository ID for {repo_name}: {e}")
    return repo_ids

def upload_items(target, item_type, items, is_org=True):
    """
    Upload secrets or variables to an organization or repository.
    """
    for item in items:
        item = {key.lower(): value for key, value in item.items()}
        try:
            existing_item = None
            try:
                if item_type == 'secrets':
                    existing_item = target.get_secret(item['name'])
                elif item_type == 'variables':
                    existing_item = target.get_variable(item['name'])

                if existing_item.name.lower() == item['name'].lower():
                    logging.warning(f"{item_type[:-1].capitalize()} '{item['name']}' already exists in {'organization' if is_org else 'repository'}{'' if is_org else f' {target.name}'}")
                    continue
            except Exception as e:
                if '404' not in str(e):
                    raise e
                
            # Handle visibility and selected repositories
            visibility = item.get('visibility', 'all')

            if visibility not in ['private', 'selected']:
                visibility = 'all'
            
            if visibility == 'selected':
                selected_repos = item.get('selectedrepositories', '')
                selected_repo_names = selected_repos.split(',')
                selected_repo_objects = get_repo_ids(target, selected_repo_names)

            if is_org:
                if item_type == 'secrets':
                    if visibility == 'selected':
                        target.create_secret(item['name'], item['value'], visibility=visibility, selected_repositories=selected_repo_objects)
                    else:
                        target.create_secret(item['name'], item['value'], visibility=visibility)
                elif item_type == 'variables':
                    if visibility == 'selected':
                        target.create_variable(item['name'], item['value'], visibility=visibility, selected_repositories=selected_repo_objects)
                    else:
                        target.create_variable(item['name'], item['value'], visibility=visibility)
            else:
                if item_type == 'secrets':
                    target.create_secret(item['name'], item['value'])
                elif item_type == 'variables':
                    target.create_variable(item['name'], item['value'])
            logging.info(f"Uploaded {item_type[:-1]} '{item['name']}' to {f'organization' if is_org else 'repository'}{'' if is_org else f' {target.name}'}")
        except Exception as e:
            logging.error(f"Failed to upload {item_type[:-1]} '{item['name']}' to {'organization' if is_org else 'repository'}{'' if is_org else f' {target.name}'}: {e}")

def read_and_verify_csv(file_path, scope):
    """
    Read secrets and variables from a CSV file and verify headers based on the scope.
    """
    try:
        if not file_path.endswith('.csv'):
            raise ValueError("Invalid file format. Please provide a valid CSV file.")
        
        df = pd.read_csv(file_path, on_bad_lines='skip')

        required_headers_org = {'type', 'name', 'value', 'visibility', 'selectedrepositories'}
        required_headers_repo = {'type', 'name', 'value', 'repository'}

        df.columns = map(str.lower, df.columns)
        headers = set(df.columns)
        
        for index, row in df.iterrows():
            item_type = row['type'].lower()
            valid_types = []
            
            if scope in ['org', 'both']:
                valid_types.extend(['org_secret', 'org_variable'])
            if scope in ['repo', 'both']:
                valid_types.extend(['repo_secret', 'repo_variable'])
            
            if item_type not in valid_types:
                logging.error(f"Invalid type '{item_type}' in row {index + 2}. Valid types for scope '{scope}': {valid_types}")
                return []
            
        if scope == 'org':
            if not required_headers_org.issubset(headers):
                logging.error(f"Missing headers for org scope. Required headers: {required_headers_org}")
                return []
        elif scope == 'repo':
            if not required_headers_repo.issubset(headers):
                logging.error(f"Missing headers for repo scope. Required headers: {required_headers_repo}")
                return []
        elif scope == 'both':
            if not (required_headers_org.issubset(headers) and required_headers_repo.issubset(headers)):
                logging.error(f"Missing headers for both scope. Required headers: {required_headers_org.union(required_headers_repo)}")
                return []

        return df.to_dict(orient='records')
    except Exception as e:
        logging.error(f"Failed to read CSV file {file_path}: {e}")
        return []

def fetch_data(org, file_name, fetch_values, auth_token, org_name, scope):
    # Fetch organization level variables and secrets and export to Excel
    if scope in ['both', 'org']:
        for item_type in ['variables', 'secrets']:
            items = get_items_org(org, item_type, fetch_values, auth_token, org_name)
            export_to_excel(items, file_name, f'org_{item_type}')

    # Fetch repository level variables and secrets and export to Excel
    if scope in ['both', 'repo']:
        repo_variables = []
        repo_secrets = []
        repo_env_variables = []  
        repo_env_secrets = []

        repos = list(org.get_repos())
        logging.info(f"Total repositories: {len(repos)}")

        for count, repo in enumerate(repos, start=1):
            logging.info(f"{count}:{repo.name}")
            repo_variables.extend(get_items_repo(repo, 'variables', fetch_values))
            repo_secrets.extend(get_items_repo(repo, 'secrets', fetch_values))
            repo_env_variables.extend(get_env_items_repo(repo, 'variables', fetch_values))
            repo_env_secrets.extend(get_env_items_repo(repo, 'secrets', fetch_values))

        for item_type, items in zip(['variables', 'secrets', 'env_variables', 'env_secrets'], [repo_variables, repo_secrets, repo_env_variables, repo_env_secrets]):
            export_to_excel(items, file_name, f'repo_{item_type}')

def update_data(org, csv_file_path, scope):
    # Read items from CSV file
    csv_items = read_and_verify_csv(csv_file_path, scope)
    csv_items = [{key.lower(): value for key, value in item.items()} for item in csv_items]

    if scope in ['org', 'both']:
        # Upload organization level variables and secrets from CSV
        org_secrets = [item for item in csv_items if item['type'] == 'org_secret']
        org_variables = [item for item in csv_items if item['type'] == 'org_variable']
        upload_items(org, 'secrets', org_secrets, is_org=True)
        upload_items(org, 'variables', org_variables, is_org=True)

    if scope in ['repo', 'both']:
        # Upload repository level variables and secrets from CSV 
        for repo in org.get_repos():
            repo_secrets = [item for item in csv_items if item['type'] == 'repo_secret' and item['repository'] == repo.name]
            repo_variables = [item for item in csv_items if item['type'] == 'repo_variable' and item['repository'] == repo.name]
            upload_items(repo, 'secrets', repo_secrets, is_org=False)
            upload_items(repo, 'variables', repo_variables, is_org=False)

# Argument parser 
parser = argparse.ArgumentParser(description='GitHub Secrets and Variables Manager')
subparsers = parser.add_subparsers(dest='command', help='Sub-command help')

# Create the parser for the "fetch" action
fetch_parser = subparsers.add_parser('fetch', help='Fetch secrets and variables')
fetch_parser.add_argument('--org', required=True, help='GitHub organization name')
fetch_parser.add_argument('--token', required=True, help='GitHub personal access token')
fetch_parser.add_argument('--fetch-values', action='store_true', help='Fetch variable values if set')
fetch_parser.add_argument('--scope', choices=['org', 'repo', 'both'], default='both', help='Scope to fetch: org, repo, or both (default: both)')

# Create the parser for the "update" action
update_parser = subparsers.add_parser('update', help='Update secrets and variables')
update_parser.add_argument('--org', required=True, help='GitHub organization name')
update_parser.add_argument('--token', required=True, help='GitHub personal access token')
update_parser.add_argument('--scope', choices=['org', 'repo', 'both'], default='both', help='Scope to update: org, repo, or both (default: both)')
update_parser.add_argument('--csv', required=True, help='Path to the CSV file containing secrets and variables')

args = parser.parse_args()

# Set organization and authentication token
try:
    g = Github(args.token)
    org = g.get_organization(args.org)
except Exception as e:
    logging.error(f"Failed to fetch data from GitHub: {e}")
    exit(1)

if args.command == 'fetch':
    logging.info(f"Fetching data for organization: {args.org}")
    file_name = f"{args.org}_output.xlsx"
    if os.path.exists(file_name):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"{args.org}_output_{timestamp}.xlsx"
    fetch_data(org, file_name, args.fetch_values, args.token, args.org, args.scope)
    logging.info(f"Output saved to: {os.getcwd()}\\{file_name}")
elif args.command == 'update':
    logging.info(f"Updating data for organization: {args.org}")
    update_data(org, args.csv, args.scope)
    logging.info("Done!")
