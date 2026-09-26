"""
Prompt Injection and Malicious Content Detector.
"""

from typing import Dict, Any, List, Tuple
import re


class PromptInjectionDetector:
    def __init__(self):
        # Known adversarial and jailbreak trigger phrases
        self.injection_patterns = [
            r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
            r"disregard\s+(all\s+)?(previous|prior)\s+instructions",
            r"system\s+prompt\s+override",
            r"you\s+are\s+now\s+(in\s+)?(developer\s+mode|dan|jailbroken)",
            r"print\s+(your\s+)?(system\s+prompt|initial\s+instructions)",
            r"output\s+all\s+environment\s+variables",
            r"<\s*script\s*>",
            r"\[\s*system\s*\]:\s*override",
            r"admin\s+mode\s+activated",
        ]
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.injection_patterns]

    def scan(self, text: str) -> Tuple[bool, List[str]]:
        """Scan text for injection signatures."""
        if not text or not isinstance(text, str):
            return False, []
            
        matches = []
        for pattern in self._compiled:
            found = pattern.findall(text)
            if found:
                matches.append(pattern.pattern)
                
        return len(matches) > 0, matches

    def sanitize_untrusted_data(self, data: Any) -> Any:
        """Wrap untrusted tool output in isolated XML tags and neutralize raw injection phrases."""
        if isinstance(data, str):
            is_injected, patterns = self.scan(data)
            if is_injected:
                # Neutralize injection text
                sanitized = data
                for pattern in self._compiled:
                    sanitized = pattern.sub("[REDACTED_ADVERSARIAL_INSTRUCTION]", sanitized)
                return f"<untrusted_external_content is_flagged='true'>\n{sanitized}\n</untrusted_external_content>"
            else:
                return f"<untrusted_external_content>\n{data}\n</untrusted_external_content>"
        elif isinstance(data, dict):
            return {k: self.sanitize_untrusted_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.sanitize_untrusted_data(item) for item in data]
        return data
