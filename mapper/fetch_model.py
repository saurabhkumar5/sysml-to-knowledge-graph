"""
Step 4: read the SysML v2 model from the SysML v2 REST API (SysON) and save it as JSON.

Usage (from the project root):
    python3 mapper/fetch_model.py
    python3 mapper/fetch_model.py --project <PROJECT_ID>

Output:
    data/elements.json   -> all model elements as returned by the API
    a short summary in the terminal (how many elements of each @type)
"""
import argparse
import collections
import json
import os
import urllib.request

API = os.environ.get("SYSML_API", "http://localhost:8080/api/rest")
DEFAULT_PROJECT = "46bf6597-b0e2-4343-9f4b-04a600b6b627"


def get_json(url):
    """Send one GET request (the 'order to the waiter') and return the JSON answer."""
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def name_of(element):
    """SysML v2 elements can carry their name in 'declaredName' or 'name'."""
    return element.get("declaredName") or element.get("name") or ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="SysON project id")
    args = parser.parse_args()

    # 1. Find the latest commit of the project (SysON has exactly one)
    commits = get_json(f"{API}/projects/{args.project}/commits")
    commit_id = commits[-1]["@id"]
    print(f"Project : {args.project}")
    print(f"Commit  : {commit_id}")

    # 2. Get all elements of that commit
    elements = get_json(f"{API}/projects/{args.project}/commits/{commit_id}/elements")
    print(f"Elements: {len(elements)}")

    # 3. Save them for the mapper (step 6)
    os.makedirs("data", exist_ok=True)
    with open("data/elements.json", "w", encoding="utf-8") as f:
        json.dump(elements, f, indent=2)
    print("Saved   : data/elements.json")

    # 4. Summary: how many elements of each type?
    counts = collections.Counter(e.get("@type", "?") for e in elements)
    print("\nElements by @type (top 15):")
    for element_type, count in counts.most_common(15):
        print(f"  {count:4d}  {element_type}")

    # 5. Show our battery part as an example
    for e in elements:
        if e.get("@type") == "PartUsage" and name_of(e) == "battery":
            print("\nExample - the battery PartUsage (first 12 fields):")
            for key in list(e.keys())[:12]:
                print(f"  {key}: {json.dumps(e[key])[:90]}")
            break


if __name__ == "__main__":
    main()
