import os
import pandas as pd
import requests
import json
import re
import time
import logging
from urllib.parse import urlparse
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Delete the debug log file at startup so that it is fresh for each run.
LOG_FILE = 'cons_debug.txt'
if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

# Configure logging to write detailed debug output to cons_debug.txt.
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    filemode='w'
)

def result_matches_org(org_name: str, result: Dict) -> bool:
    """Return True if any token from the organization name (ignoring common words) is found in the result's title or description."""
    org_tokens = org_name.lower().split()
    common_words = {"the", "of", "and", "company", "inc", "co", "-"}
    org_tokens = [token for token in org_tokens if token not in common_words]
    title = result.get('title', '').lower()
    desc = result.get('description', '').lower()
    return any(token in title or token in desc for token in org_tokens)

def url_belongs_to_org(org_name: str, url: str) -> bool:
    """
    Parse the URL and return True if any token (ignoring common words)
    from the organization name appears in the hostname.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    org_tokens = org_name.lower().split()
    common_words = {"the", "of", "and", "company", "inc", "co", "-"}
    org_tokens = [token for token in org_tokens if token not in common_words]
    return any(token in hostname for token in org_tokens)

class DecarbonizationAnalyzer:
    def __init__(self, brave_api_key: str, anthropic_api_key: str):
        """
        Initialize the analyzer with API keys and endpoint URLs.
        """
        self.brave_api_key = brave_api_key
        self.anthropic_api_key = anthropic_api_key
        self.brave_search_endpoint = "https://api.search.brave.com/res/v1/web/search"
        self.anthropic_endpoint = "https://api.anthropic.com/v1/messages"

    def search_organization(self, org_name: str) -> List[Dict]:
        """
        Searches Brave for pages related to the organization's decarbonization goals.
        Enforces a one‑second delay between requests and retries once if rate limited.
        Debug details are written to cons_debug.txt.
        """
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.brave_api_key
        }
        query = f"{org_name} decarbonization goals net zero carbon neutral target date"
        params = {"q": query, "count": 5}
        logging.debug(f"Searching for organization: {org_name}")
        logging.debug(f"Query: {query}")
        logging.debug(f"Request params: {params}")

        results = []
        try:
            response = requests.get(self.brave_search_endpoint, headers=headers, params=params)
            if response.status_code == 429:
                logging.error(f"Rate limit hit for {org_name}. Waiting 5 seconds before retrying...")
                time.sleep(5)
                response = requests.get(self.brave_search_endpoint, headers=headers, params=params)
            logging.debug(f"Brave API response status for {org_name}: {response.status_code}")
            if response.status_code == 200:
                try:
                    json_data = response.json()
                    results = json_data.get("web", {}).get("results", [])
                    logging.debug(f"Search results for {org_name}: {results}")
                except Exception as e:
                    logging.error(f"Error parsing JSON response for {org_name}: {e}")
                    logging.error("Raw response text: " + response.text)
            else:
                logging.error(f"Error searching for {org_name}: {response.status_code}")
                logging.error("Response text: " + response.text)
        except Exception as e:
            logging.error(f"Exception during search for {org_name}: {e}")
        finally:
            time.sleep(1)
        return results

    def analyze_search_results(self, org_name: str, search_results: List[Dict]) -> Dict:
        """
        Uses Anthropic's Claude to determine if the organization has a decarbonization goal,
        extracting the target date, source URL, and a short description.
        The prompt instructs the model to only use information from the organization's official website
        or its official press releases.
        Debug output is written to cons_debug.txt.
        """
        if not search_results:
            logging.error(f"No search results for {org_name}; skipping Anthropic API call.")
            return {
                "organization": org_name,
                "has_goal": "Not Found",
                "target_date": None,
                "source_url": None,
                "description": ""
            }
        
        # Build context from search results.
        context = f"Search results for {org_name}:\n"
        for result in search_results:
            context += f"Title: {result.get('title')}\n"
            context += f"Description: {result.get('description')}\n"
            context += f"URL: {result.get('url')}\n\n"
        
        # Strengthen the prompt:
        prompt = (
            f"Based on these search results, determine the following for {org_name} using only information from "
            f"the organization's official website or its official press releases (do not use third-party sites):\n"
            f"1. Does {org_name} have a stated decarbonization goal? (Answer Yes, No, or Not Found)\n"
            f"2. If yes, what is their target date?\n"
            f"3. What is the source URL for this information?\n"
            f"4. In one to two sentences, provide a short description summarizing the organization's decarbonization goal, mission, or strategy.\n\n"
            f"Search results:\n{context}\n"
            f"Please provide the answers in JSON format with keys: has_goal, target_date, source_url, description"
        )
        logging.debug(f"Prompt for Anthropic API for {org_name}:\n{prompt}")

        data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]
        }
        anthro_headers = {
            "x-api-key": self.anthropic_api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        logging.debug(f"Posting to Anthropic API for {org_name} with data:\n{json.dumps(data, indent=2)}")
        logging.debug(f"Request headers: {anthro_headers}")

        try:
            response = requests.post(self.anthropic_endpoint, headers=anthro_headers, json=data)
            logging.debug(f"Anthropic API response status for {org_name}: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                logging.debug(f"Anthropic API response for {org_name}:\n{json.dumps(result, indent=2)}")
                claude_response_text = ""
                if "completion" in result:
                    claude_response_text = result["completion"]
                elif "content" in result:
                    content = result["content"]
                    if isinstance(content, list):
                        texts = [item.get("text", "") for item in content if isinstance(item, dict)]
                        claude_response_text = "\n".join(texts)
                    else:
                        claude_response_text = content
                logging.debug(f"Extracted Claude response text:\n{claude_response_text}")
                json_candidate = re.search(r'({.*})', claude_response_text, re.DOTALL)
                if json_candidate:
                    json_str = json_candidate.group(1)
                    try:
                        parsed_response = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logging.error(f"Error decoding JSON from Claude's response for {org_name}: {e}")
                        parsed_response = {}
                else:
                    logging.error(f"No JSON candidate found in Claude's response for {org_name}.")
                    parsed_response = {}
            else:
                logging.error(f"Error calling Anthropic API for {org_name}: {response.status_code}")
                logging.error("Response text: " + response.text)
                parsed_response = {}
        except Exception as e:
            logging.error(f"Error in API call for {org_name}: {e}")
            parsed_response = {}

        # Fallback for source_url: only accept a URL if it appears to be from an official source.
        if not parsed_response.get("source_url"):
            for r in search_results:
                url = r.get("url", "")
                if url and result_matches_org(org_name, r) and url_belongs_to_org(org_name, url):
                    parsed_response["source_url"] = url
                    break

        # Fallback for target_date: only from a result that appears to be from the official source.
        if not parsed_response.get("target_date"):
            for r in search_results:
                if result_matches_org(org_name, r) and url_belongs_to_org(org_name, r.get("url", "")):
                    desc = r.get("description", "")
                    match = re.search(r'\b(20\d{2})\b', desc)
                    if match:
                        parsed_response["target_date"] = match.group(1)
                        break

        # Fallback for description: only if the result appears relevant and from an official source.
        if not parsed_response.get("description"):
            for r in search_results:
                desc = r.get("description", "")
                if (("decarbon" in desc.lower() or "net zero" in desc.lower()) and 
                    result_matches_org(org_name, r) and url_belongs_to_org(org_name, r.get("url", ""))):
                    parsed_response["description"] = desc.strip()[:250]
                    break

        return {
            "organization": org_name,
            "has_goal": parsed_response.get("has_goal", "Not Found"),
            "target_date": parsed_response.get("target_date"),
            "source_url": parsed_response.get("source_url"),
            "description": parsed_response.get("description", "")
        }

def analyze_decarbonization_goals(org_list: List[str], output_csv: str):
    """
    Processes a list of organizations, analyzes decarbonization goals,
    and writes the results to a CSV file.
    Only minimal progress messages and final summary are printed to the console.
    Detailed debug output is written to cons_debug.txt.
    """
    # Get API keys from environment variables with error handling
    brave_api_key = os.getenv("BRAVE_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    
    # Check if API keys are available
    if not brave_api_key or not anthropic_api_key:
        missing_keys = []
        if not brave_api_key:
            missing_keys.append("BRAVE_API_KEY")
        if not anthropic_api_key:
            missing_keys.append("ANTHROPIC_API_KEY")
        
        print(f"Error: Missing required API keys: {', '.join(missing_keys)}")
        print("Please create a .env file with the required API keys. See .env.example for the format.")
        return
    
    analyzer = DecarbonizationAnalyzer(
        brave_api_key=brave_api_key,
        anthropic_api_key=anthropic_api_key
    )
    
    results = []
    for org in org_list:
        print(f"\nAnalyzing {org}...")
        search_results = analyzer.search_organization(org)
        analysis = analyzer.analyze_search_results(org, search_results)
        results.append(analysis)
        time.sleep(1)
    
    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False)
    print(f"\nCSV saved to {output_csv}\n")
    
    total_orgs = len(df)
    orgs_with_goals = len(df[df['has_goal'].str.lower() == 'yes'])
    print("Organization,Decarbonization Goal?,Target Date,Source URL,Description")
    for _, row in df.iterrows():
        print(f"{row['organization']},{row['has_goal']},{row['target_date']},{row['source_url']},{row['description']}")
    print("\nDecarbonization Goals Analysis Summary")
    print("-" * 30)
    print(f"Total Organizations: {total_orgs}")
    print(f"Organizations with Goals: {orgs_with_goals} ({orgs_with_goals/total_orgs*100:.1f}%)")

if __name__ == "__main__":
    org_list = [
        "Consolidated Edison Company of New York",
        "Veolia Energy NA - Philadelphia",
        "Columbia Energy Center",
        "Downtown Milwaukee",
        "University of Wisconsin - Whitewater",
        "University of Delaware"
    ]
    
    analyze_decarbonization_goals(org_list, 'decarbonization_goals.csv')