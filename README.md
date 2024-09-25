# GitHub Secrets and Variables Management

This Python script allows you to fetch and update secrets and variables from a GitHub organization and its repositories. The script can export the fetched data to an Excel file and update secrets and variables from a CSV file.

## Requirements

- Python 3.6 or higher
- `github` Python module
- `pandas` Python module
- `openpyxl` Python module
- `requests` Python module

You can install these modules using pip:

```bash
pip install -r requirements.txt
```

## Usage
You can run the script from the command line with the following arguments:

- `--org`: The name of the GitHub organization (required)
- `--token`: GitHub personnel access token
- `--fetch_values`: Fetch variable values if set (optional, only for fetch command)
- `--scope`: Scope to fetch or update: both, org, or repo (default: both)
- `--csv`: Path to the CSV file containing secrets and variables (required for update action)


### Examples:

Fetch secrets and variables from both organization and repositories (default action):
```bash
python ghVarSecrets.py fetch --org MyOrganization --token MyToken
```
Fetch only org secrets and variables:
```bash
python ghVarSecrets.py fetch --org MyOrganization --token MyToken --scope org
```
Fetch only repository secrets and variables:
```bash
python ghVarSecrets.py fetch --org MyOrganization --token MyToken --scope org
```
Update secrets and variables from a CSV file:
```bash
python ghVarSecrets.py update --org MyOrganization --token MyToken --scope both --csv path/to/secrets_and_variables.csv
```

### CSV File Format
The CSV file should have the following columns:

### Organization:
- `type`: Type of the item (org_secret or org_variable)
- `name`: Name of the secret or variable
- `value`: Value of the secret or variable
- `visibility`: Visibility of the secret or variable (all, private, or selected)
- `selectedrepositories`: Comma-separated list of selected repositories (required if visibility is selected)
### Note: By default, the visibility will be set to all repositories within the organization if nothing is provided for organization variables and secrets.
Example:
```bash
type,name,value,visibility,selectedrepositories
org_secret,ORG_SECRET_KEY,secret_value,selected,repo1,repo2
org_variable,ORG_VARIABLE_KEY,variable_value,private,
```

### Repository:
- `type`: Type of the item (repo_secret or repo_variable)
- `name`: Name of the secret or variable
- `value`: Value of the secret or variable
- `repository`: Name of the repository

Example:
```bash
type,name,value,visibility,selectedrepositories
repo_secret,REPO_SECRET_KEY,secret_value,repo_name
repo_variable,REPO_VARIABLE_KEY,variable_value,repo_name
```
