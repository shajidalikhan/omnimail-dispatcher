import re
from typing import Dict, Any, List
from jinja2 import Environment, BaseLoader, select_autoescape

# Spam trigger words and phrases for cold outreach hygiene
SPAM_TRIGGER_WORDS = [
    "100% free", "act now", "apply now", "as seen on", "buy now", "click here",
    "dear friend", "double your income", "earn extra cash", "exclusive deal",
    "fast cash", "financial freedom", "free gift", "free money", "get out of debt",
    "guaranteed", "increase sales", "limited time", "make money", "million dollars",
    "no cost", "no fees", "no strings attached", "once in a lifetime", "order now",
    "risk free", "save big", "special promotion", "urgent", "winner", "you have won"
]

PERSONALIZATION_GUIDELINES = [
    {
        "title": "1. Dynamic Opening & Salutations",
        "description": "Never send generic 'Dear Sir/Madam' or 'To Whom It May Concern'. Use dynamic tags such as 'Dear Prof. {{Name}}' or 'Hi {{First_Name}}'. Always include a sensible fallback using Jinja syntax:",
        "example": "Dear {{Name | default('Colleague')}},"
    },
    {
        "title": "2. Tailored Context & Shared Relevance",
        "description": "Cold emails feel personal when they mention a specific paper, university, or project. Use custom columns like {{University}} or {{Research_Area}} directly in your message body:",
        "example": "I came across your work in {{Research_Area | default('your laboratory')}} at {{University | default('your institution')}}..."
    },
    {
        "title": "3. Subject Line Hygiene",
        "description": "Keep subject lines under 50 characters, lowercase or title-case, and avoid hype or exclamation points. Add dynamic parameters to dramatically boost open rates:",
        "example": "Inquiry regarding {{Research_Area}} research / Quick question, {{Name}}"
    },
    {
        "title": "4. Single Clear Call To Action (CTA)",
        "description": "Don't overload the recipient with multiple requests or lengthy attachments. Ask one low-friction, polite question at the end:",
        "example": "Would you have 10 minutes next Tuesday for a brief introductory call?"
    },
    {
        "title": "5. Anti-Spam & Deliverability Rules",
        "description": "Avoid ALL-CAPS words, excessive exclamation marks (!!!), large images without text, and URL shorteners (bit.ly). Ensure an interval delay (3–5s) between sends."
    }
]

DEFAULT_SUBJECT = "Research Collaboration Inquiry - {{University | default('Your Institution')}}"
DEFAULT_BODY_HTML = """<p>Dear {{Name | default('Colleague')}},</p>

<p>I hope this email finds you well.</p>

<p>I am writing to you from the Department of Computer Science regarding your impactful research in <strong>{{Research_Area | default('Computer Science')}}</strong> at <em>{{University | default('your institution')}}</em>.</p>

<p>We are currently exploring collaborative academic opportunities and would be honored to discuss potential synergy with your ongoing initiatives.</p>

<p>Would you be open to a brief 10-minute introductory conversation sometime next week?</p>

<p>Warm regards,<br>
<strong>{{Sender_Name | default('Research Team')}}</strong><br>
M.Tech Research Initiative</p>
"""

DEFAULT_BODY_TEXT = """Dear {{Name | default('Colleague')}},

I hope this email finds you well.

I am writing to you from the Department of Computer Science regarding your impactful research in {{Research_Area | default('Computer Science')}} at {{University | default('your institution')}}.

We are currently exploring collaborative academic opportunities and would be honored to discuss potential synergy with your ongoing initiatives.

Would you be open to a brief 10-minute introductory conversation sometime next week?

Warm regards,
{{Sender_Name | default('Research Team')}}
M.Tech Research Initiative
"""

def extract_variables(text: str) -> List[str]:
    """Find all variable tokens in format {{ variable_name }} or {{ var | default(...) }}."""
    matches = re.findall(r"\{\{\s*([a-zA-Z0-9_]+)", text)
    return sorted(list(set(matches)))

def analyze_template_hygiene(subject: str, body: str) -> Dict[str, Any]:
    """Inspect subject and body for spam keywords, subject length, and personalization health."""
    content_lower = f"{subject} {body}".lower()
    found_spam_words = [w for w in SPAM_TRIGGER_WORDS if w in content_lower]
    
    subject_len = len(subject.strip())
    subject_has_vars = bool(re.search(r"\{\{.*?\}\}", subject))
    body_has_vars = bool(re.search(r"\{\{.*?\}\}", body))
    
    score = 100
    warnings = []
    
    if len(found_spam_words) > 0:
        score -= min(30, len(found_spam_words) * 10)
        warnings.append(f"Spam trigger words detected: {', '.join(found_spam_words)}")
        
    if subject_len > 60:
        score -= 10
        warnings.append(f"Subject line is {subject_len} characters long (recommended: under 50 characters).")
        
    if not subject_has_vars:
        warnings.append("Consider adding a dynamic tag (e.g. {{Name}} or {{University}}) to the subject line for higher open rates.")
        
    if not body_has_vars:
        score -= 20
        warnings.append("Body does not contain any personalization variables (e.g. {{Name}}). It may be flagged as a mass broadcast.")

    return {
        "score": max(0, score),
        "found_spam_words": found_spam_words,
        "warnings": warnings,
        "subject_length": subject_len,
        "is_personalized": body_has_vars
    }

def render_template(template_str: str, context: Dict[str, Any]) -> str:
    """Render a Jinja2 template with provided context dictionary."""
    env = Environment(
        loader=BaseLoader(),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True
    )
    
    # Handle simple {{Field}} without requiring complex filters
    # If a field is missing in context, provide empty string instead of undefined crash
    try:
        t = env.from_string(template_str)
        return t.render(**context)
    except Exception as e:
        # Fallback to safe string replacement if Jinja encounters syntax issue
        rendered = template_str
        for k, v in context.items():
            rendered = rendered.replace(f"{{{{{k}}}}}", str(v))
        return rendered
