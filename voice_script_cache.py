"""
Voice Script Cache for RapidSales.ai

This module handles caching of AI-generated voice scripts to reduce
latency and API costs. Scripts are cached by industry + product category
since the same base script works for all leads in that segment.

Usage:
    cache = VoiceScriptCache(redis_client, llm_client)
    script = cache.get_script("real_estate", "crm", "John Smith", "Acme Realty")
"""

import json
import time
import logging
from typing import Optional, Dict, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Fallback templates when LLM is unavailable
# These are generic but professional scripts for common industries
FALLBACK_TEMPLATES = {
    "real_estate": """
Hi {lead_name}, this is calling on behalf of {client_company}. 
I'm reaching out because we work with real estate professionals like yourself 
to help streamline operations and close more deals. 
Many agents in your area have seen great results with our solution. 
Would you have a few minutes this week to learn how we might help {lead_company}?
""",
    "healthcare": """
Hi {lead_name}, this is calling on behalf of {client_company}. 
We specialize in helping healthcare organizations improve efficiency 
while maintaining the highest standards of patient care. 
I'd love to share how practices similar to {lead_company} have benefited. 
Do you have a few minutes to chat this week?
""",
    "finance": """
Hi {lead_name}, this is calling on behalf of {client_company}. 
We help financial services firms like {lead_company} optimize their operations 
and better serve their clients. 
I'd like to briefly share some results we've achieved for similar organizations. 
Would you have time for a quick call this week?
""",
    "technology": """
Hi {lead_name}, this is calling on behalf of {client_company}. 
We work with tech companies to solve complex challenges and accelerate growth. 
I think there might be a good fit with what {lead_company} is doing. 
Could we schedule a brief call to explore this?
""",
    "retail": """
Hi {lead_name}, this is calling on behalf of {client_company}. 
We help retail businesses increase sales and improve customer experience. 
I'd love to share how we've helped companies similar to {lead_company}. 
Do you have a few minutes this week to connect?
""",
    "default": """
Hi {lead_name}, this is calling on behalf of {client_company}. 
We help businesses like {lead_company} achieve better results. 
I'd like to share how we might be able to help you as well. 
Would you have a few minutes for a quick conversation this week?
"""
}


class VoiceScriptCache:
    """
    Caches voice scripts by industry and product category.
    
    Cache key format: voice:v1:{industry}:{product_category}
    TTL: 24 hours
    
    On cache miss, calls LLM to generate script, then caches result.
    On LLM failure, falls back to template library.
    """
    
    CACHE_VERSION = "v1"
    DEFAULT_TTL = 86400  # 24 hours in seconds
    
    def __init__(self, redis_client, llm_client, ttl: int = None):
        """
        Args:
            redis_client: Redis connection (must have get, set, delete methods)
            llm_client: LLM client with generate_script method
            ttl: Cache TTL in seconds (default 24 hours)
        """
        self.redis = redis_client
        self.llm = llm_client
        self.ttl = ttl or self.DEFAULT_TTL
        
        # Track metrics for monitoring
        self.metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "llm_calls": 0,
            "llm_failures": 0,
            "fallback_used": 0
        }
    
    def _make_cache_key(self, industry: str, product_category: str) -> str:
        """Generate normalized cache key."""
        industry_norm = industry.lower().strip().replace(" ", "_")
        product_norm = product_category.lower().strip().replace(" ", "_")
        return f"voice:{self.CACHE_VERSION}:{industry_norm}:{product_norm}"
    
    def _personalize_script(self, template: str, lead_name: str, 
                           lead_company: str, client_company: str) -> str:
        """Insert lead-specific details into script template."""
        return template.format(
            lead_name=lead_name,
            lead_company=lead_company,
            client_company=client_company
        )
    
    def _get_fallback_template(self, industry: str) -> str:
        """Get template for industry, or default if not found."""
        industry_lower = industry.lower()
        
        # Check for exact match
        if industry_lower in FALLBACK_TEMPLATES:
            return FALLBACK_TEMPLATES[industry_lower]
        
        # Check for partial match
        for key in FALLBACK_TEMPLATES:
            if key in industry_lower or industry_lower in key:
                return FALLBACK_TEMPLATES[key]
        
        return FALLBACK_TEMPLATES["default"]
    
    def get_script(self, industry: str, product_category: str,
                   lead_name: str, lead_company: str, 
                   client_company: str) -> Tuple[str, Dict]:
        """
        Get voice script for a lead.
        
        Checks cache first, generates on miss, falls back to template on failure.
        
        Args:
            industry: Lead's industry (e.g., "real_estate")
            product_category: Client's product type (e.g., "crm")
            lead_name: Name of the person being called
            lead_company: Lead's company name
            client_company: Name of our client (the seller)
            
        Returns:
            Tuple of (personalized_script, metrics_dict)
        """
        start_time = time.time()
        cache_key = self._make_cache_key(industry, product_category)
        
        metrics = {
            "cache_hit": False,
            "llm_called": False,
            "fallback_used": False,
            "latency_ms": 0
        }
        
        # Try cache first
        try:
            cached = self.redis.get(cache_key)
            if cached:
                logger.info(f"Cache hit for {cache_key}")
                self.metrics["cache_hits"] += 1
                metrics["cache_hit"] = True
                
                template = cached if isinstance(cached, str) else cached.decode()
                script = self._personalize_script(
                    template, lead_name, lead_company, client_company
                )
                
                metrics["latency_ms"] = int((time.time() - start_time) * 1000)
                return script, metrics
                
        except Exception as e:
            logger.warning(f"Redis error on get: {e}")
            # Continue to LLM call
        
        # Cache miss - call LLM
        logger.info(f"Cache miss for {cache_key}, calling LLM")
        self.metrics["cache_misses"] += 1
        metrics["llm_called"] = True
        
        try:
            self.metrics["llm_calls"] += 1
            template = self.llm.generate_script(industry, product_category)
            
            # Cache the result
            try:
                self.redis.setex(cache_key, self.ttl, template)
                logger.info(f"Cached script for {cache_key}")
            except Exception as e:
                logger.warning(f"Redis error on set: {e}")
                # Continue anyway, we have the script
            
            script = self._personalize_script(
                template, lead_name, lead_company, client_company
            )
            
            metrics["latency_ms"] = int((time.time() - start_time) * 1000)
            return script, metrics
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            self.metrics["llm_failures"] += 1
        
        # LLM failed - use fallback template
        logger.warning(f"Using fallback template for {industry}")
        self.metrics["fallback_used"] += 1
        metrics["fallback_used"] = True
        
        template = self._get_fallback_template(industry)
        script = self._personalize_script(
            template, lead_name, lead_company, client_company
        )
        
        metrics["latency_ms"] = int((time.time() - start_time) * 1000)
        return script, metrics
    
    def invalidate(self, industry: str, product_category: str) -> bool:
        """
        Remove a cached script.
        
        Call this when a client updates their product offering.
        """
        cache_key = self._make_cache_key(industry, product_category)
        try:
            self.redis.delete(cache_key)
            logger.info(f"Invalidated cache for {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to invalidate {cache_key}: {e}")
            return False
    
    def warm_cache(self, combinations: list) -> Dict:
        """
        Pre-generate scripts for common industry/product combinations.
        
        Args:
            combinations: List of (industry, product_category) tuples
            
        Returns:
            Dict with success/failure counts
        """
        results = {"success": 0, "failed": 0}
        
        for industry, product_category in combinations:
            cache_key = self._make_cache_key(industry, product_category)
            
            # Skip if already cached
            try:
                if self.redis.get(cache_key):
                    logger.info(f"Already cached: {cache_key}")
                    results["success"] += 1
                    continue
            except:
                pass
            
            # Generate and cache
            try:
                template = self.llm.generate_script(industry, product_category)
                self.redis.setex(cache_key, self.ttl, template)
                logger.info(f"Warmed cache for {cache_key}")
                results["success"] += 1
            except Exception as e:
                logger.error(f"Failed to warm {cache_key}: {e}")
                results["failed"] += 1
        
        return results
    
    def get_metrics(self) -> Dict:
        """Return current metrics for monitoring."""
        total = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        hit_rate = self.metrics["cache_hits"] / total if total > 0 else 0
        
        return {
            **self.metrics,
            "total_requests": total,
            "hit_rate": round(hit_rate, 3)
        }


# Mock LLM client for testing
class MockLLMClient:
    """Simulates LLM for testing without API calls."""
    
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.call_count = 0
    
    def generate_script(self, industry: str, product_category: str) -> str:
        self.call_count += 1
        
        if self.should_fail:
            raise Exception("Simulated LLM failure")
        
        return f"""
Hi {{lead_name}}, this is calling on behalf of {{client_company}}.
We specialize in {product_category} solutions for the {industry} industry.
Companies like {{lead_company}} have seen great results working with us.
Would you have a few minutes this week for a quick conversation?
"""


# Simple tests
def run_tests():
    """Run basic tests to verify the cache works."""
    
    print("Running tests...\n")
    
    # Use a mock Redis for testing
    class MockRedis:
        def __init__(self):
            self.data = {}
        
        def get(self, key):
            return self.data.get(key)
        
        def setex(self, key, ttl, value):
            self.data[key] = value
        
        def delete(self, key):
            if key in self.data:
                del self.data[key]
    
    # Test 1: Cache miss then hit
    print("Test 1: Cache miss followed by cache hit")
    redis = MockRedis()
    llm = MockLLMClient()
    cache = VoiceScriptCache(redis, llm)
    
    # First call - should miss and call LLM
    script1, metrics1 = cache.get_script(
        "real_estate", "crm", "John", "Acme Realty", "TechCorp"
    )
    assert metrics1["cache_hit"] == False
    assert metrics1["llm_called"] == True
    assert "John" in script1
    print("  - Cache miss: OK")
    
    # Second call - should hit cache
    script2, metrics2 = cache.get_script(
        "real_estate", "crm", "Jane", "Other Realty", "TechCorp"
    )
    assert metrics2["cache_hit"] == True
    assert metrics2["llm_called"] == False
    assert "Jane" in script2
    print("  - Cache hit: OK")
    
    # LLM should only have been called once
    assert llm.call_count == 1
    print("  - LLM call count: OK\n")
    
    # Test 2: Fallback on LLM failure
    print("Test 2: Fallback when LLM fails")
    redis2 = MockRedis()
    llm2 = MockLLMClient(should_fail=True)
    cache2 = VoiceScriptCache(redis2, llm2)
    
    script, metrics = cache2.get_script(
        "healthcare", "ehr", "Dr. Smith", "City Hospital", "MedTech"
    )
    assert metrics["fallback_used"] == True
    assert "Dr. Smith" in script
    assert "healthcare" in script.lower()
    print("  - Fallback used: OK")
    print("  - Script personalized: OK\n")
    
    # Test 3: Cache invalidation
    print("Test 3: Cache invalidation")
    redis3 = MockRedis()
    llm3 = MockLLMClient()
    cache3 = VoiceScriptCache(redis3, llm3)
    
    # Populate cache
    cache3.get_script("tech", "saas", "Bob", "StartupCo", "Vendor")
    assert llm3.call_count == 1
    
    # Verify cached
    _, metrics = cache3.get_script("tech", "saas", "Alice", "OtherCo", "Vendor")
    assert metrics["cache_hit"] == True
    
    # Invalidate
    cache3.invalidate("tech", "saas")
    
    # Should miss now
    _, metrics = cache3.get_script("tech", "saas", "Charlie", "ThirdCo", "Vendor")
    assert metrics["cache_hit"] == False
    assert llm3.call_count == 2
    print("  - Invalidation works: OK\n")
    
    # Test 4: Metrics tracking
    print("Test 4: Metrics tracking")
    final_metrics = cache.get_metrics()
    assert final_metrics["cache_hits"] == 1
    assert final_metrics["cache_misses"] == 1
    assert final_metrics["hit_rate"] == 0.5
    print(f"  - Metrics: {final_metrics}")
    print("  - Metrics correct: OK\n")
    
    print("All tests passed!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        run_tests()
    else:
        print("Voice Script Cache for RapidSales.ai")
        print("Usage: python voice_script_cache.py test")
        print("\nSee docstring and README for integration instructions.")
