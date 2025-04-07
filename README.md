# Decarbonization Goals Analyzer

This tool analyzes organization's decarbonization goals by searching for information online and processing the results using Brave Search API and Anthropic's Claude API.

## Setup

### Prerequisites

- Python 3.7+
- Brave Search API key (get one from [Brave Search API](https://brave.com/search/api/))
- Anthropic API key (get one from [Anthropic Console](https://console.anthropic.com/))

### Installation

1. Clone this repository:
   ```
   git clone https://github.com/EDITTHIS/decarbonization-analyzer.git
   cd decarbonization-analyzer
   ```

2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file:
   ```
   cp .env.example .env
   ```
   
4. Edit the `.env` file and add your API keys:
   ```
   BRAVE_API_KEY=your_brave_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key
   ```

## Usage

Run the script with:

```
python decarbonization_analyzer.py
```

The script will:
1. Search for information about organizations' decarbonization goals
2. Analyze the search results to extract key information
3. Save the results to a CSV file (`decarbonization_goals.csv`)
4. Print a summary of the findings

### Customizing the Organization List

To analyze different organizations, modify the `org_list` in `decarbonization_analyzer.py`.

## Output

The program generates:
- A CSV file with detailed results
- A console summary of findings
- A detailed debug log file (`cons_debug.txt`)