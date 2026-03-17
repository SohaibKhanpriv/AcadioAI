#!/usr/bin/env python3
"""
CLI Playground for Acadlo AI Core

A simple command-line tool to interact with the AI Core service
without needing ABP/Nuxt or any frontend.
"""
import requests
import json
import sys
from typing import Optional


class AcadloPlayground:
    """Interactive CLI playground for testing AI Core endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.tenant_id = "t_demo"
        self.user_id = "u_demo"
    
    def print_header(self, title: str):
        """Print a formatted header"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)
    
    def print_json(self, data: dict):
        """Pretty print JSON data"""
        print(json.dumps(data, indent=2, ensure_ascii=False))
    
    def test_health(self):
        """Test health endpoint"""
        self.print_header("Testing /health")
        try:
            response = requests.get(f"{self.base_url}/health")
            print(f"Status: {response.status_code}")
            self.print_json(response.json())
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_echo(self):
        """Test echo endpoint"""
        self.print_header("Testing /echo")
        payload = {
            "data": {
                "message": "Hello from playground!",
                "timestamp": "2025-11-22T10:00:00Z"
            }
        }
        try:
            response = requests.post(f"{self.base_url}/echo", json=payload)
            print(f"Status: {response.status_code}")
            self.print_json(response.json())
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def ingest_document(self, title: str, content: str, source_type: str = "policy"):
        """Ingest a document"""
        self.print_header("Ingesting Document")
        payload = {
            "tenantId": self.tenant_id,
            "externalId": f"EXT_{title.replace(' ', '_')}",
            "title": title,
            "language": "en-US",
            "sourceType": source_type,
            "visibility": {
                "roles": ["Teacher", "Admin"],
                "scopes": ["School:Demo"]
            },
            "tags": {
                "demo": "true",
                "source": "playground"
            },
            "content": {
                "type": "text",
                "value": content
            },
            "metadata": {
                "uploadedBy": self.user_id,
                "sourceName": "playground"
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/ingest/document",
                json=payload
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            self.print_json(result)
            return result.get("jobId")
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def check_job_status(self, job_id: str):
        """Check ingestion job status"""
        self.print_header(f"Checking Job Status: {job_id}")
        try:
            response = requests.get(
                f"{self.base_url}/v1/ingest/status",
                params={"jobId": job_id}
            )
            print(f"Status: {response.status_code}")
            self.print_json(response.json())
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def search(self, query: str, language: str = "en-US"):
        """Perform search"""
        self.print_header(f"Searching: {query}")
        payload = {
            "tenantId": self.tenant_id,
            "userId": self.user_id,
            "roles": ["Teacher"],
            "language": language,
            "query": query,
            "filters": {
                "sourceType": ["policy"]
            },
            "topK": 5
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/search",
                json=payload
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            self.print_json(result)
            
            # Print results in a friendly format
            results = result.get("results", [])
            if results:
                print(f"\n📊 Found {len(results)} result(s):")
                for i, r in enumerate(results, 1):
                    print(f"\n  Result {i}:")
                    print(f"    Score: {r['score']}")
                    print(f"    Title: {r['title']}")
                    print(f"    Text: {r['text'][:100]}...")
            else:
                print("\n📭 No results found")
            
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def chat(self, message: str, language: str = "en-US"):
        """Send chat message"""
        self.print_header(f"Chat Message: {message}")
        payload = {
            "tenantId": self.tenant_id,
            "userId": self.user_id,
            "roles": ["Teacher"],
            "language": language,
            "scenario": "generic",
            "message": message,
            "history": [],
            "uiContext": {
                "page": "playground"
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat",
                json=payload
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            self.print_json(result)
            
            # Print answer in a friendly format
            answer = result.get("answer", "")
            print(f"\n💬 Answer:\n{answer}")
            
            citations = result.get("citations", [])
            if citations:
                print(f"\n📚 Citations ({len(citations)}):")
                for i, c in enumerate(citations, 1):
                    print(f"  {i}. {c['title']} (Doc: {c['documentId']})")
            
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def interactive_mode(self):
        """Run interactive mode"""
        print("\n")
        print("╔═══════════════════════════════════════════════════════════════════╗")
        print("║                  Acadlo AI Core - Playground                      ║")
        print("║                   Interactive Testing Tool                        ║")
        print("╚═══════════════════════════════════════════════════════════════════╝")
        print(f"\nConnected to: {self.base_url}")
        print(f"Tenant ID: {self.tenant_id}")
        print(f"User ID: {self.user_id}")
        
        # Test connection
        if not self.test_health():
            print("\n❌ Cannot connect to service. Make sure it's running!")
            print("   Start it with: python -m app.main")
            return
        
        while True:
            print("\n" + "-" * 70)
            print("Choose an action:")
            print("  1. Test Health & Echo")
            print("  2. Ingest Document")
            print("  3. Check Job Status")
            print("  4. Search")
            print("  5. Chat")
            print("  6. Full Demo (all features)")
            print("  0. Exit")
            print("-" * 70)
            
            choice = input("\nEnter choice (0-6): ").strip()
            
            if choice == "0":
                print("\n👋 Goodbye!")
                break
            
            elif choice == "1":
                self.test_health()
                self.test_echo()
            
            elif choice == "2":
                title = input("Document title: ").strip()
                content = input("Document content: ").strip()
                if title and content:
                    job_id = self.ingest_document(title, content)
                    if job_id:
                        print(f"\n✅ Document submitted! Job ID: {job_id}")
                        input("\nPress Enter to check status...")
                        self.check_job_status(job_id)
            
            elif choice == "3":
                job_id = input("Job ID: ").strip()
                if job_id:
                    self.check_job_status(job_id)
            
            elif choice == "4":
                query = input("Search query: ").strip()
                if query:
                    self.search(query)
            
            elif choice == "5":
                message = input("Your message: ").strip()
                if message:
                    self.chat(message)
            
            elif choice == "6":
                self.run_full_demo()
            
            else:
                print("❌ Invalid choice")
    
    def run_full_demo(self):
        """Run a full demo of all features"""
        self.print_header("FULL DEMO - All Features")
        
        print("\n1️⃣  Testing Health & Echo...")
        self.test_health()
        self.test_echo()
        
        input("\n⏸️  Press Enter to continue...")
        
        print("\n2️⃣  Ingesting a sample document...")
        job_id = self.ingest_document(
            title="Student Transfer Policy",
            content="The student transfer policy requires approval from both schools. "
                   "Students must meet academic requirements and provide transcripts. "
                   "The transfer process takes approximately 2 weeks to complete."
        )
        
        if job_id:
            input("\n⏸️  Press Enter to check job status...")
            self.check_job_status(job_id)
        
        input("\n⏸️  Press Enter to continue...")
        
        print("\n3️⃣  Testing search...")
        self.search("student transfer requirements")
        
        input("\n⏸️  Press Enter to continue...")
        
        print("\n4️⃣  Testing chat...")
        self.chat("How do I transfer a student to another school?")
        
        print("\n\n✅ Demo completed!")


def main():
    """Main entry point"""
    base_url = "http://localhost:8000"
    
    # Check if custom URL provided
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    playground = AcadloPlayground(base_url)
    
    # Check if running in non-interactive mode
    if len(sys.argv) > 2 and sys.argv[2] == "--demo":
        playground.run_full_demo()
    else:
        playground.interactive_mode()


if __name__ == "__main__":
    main()

