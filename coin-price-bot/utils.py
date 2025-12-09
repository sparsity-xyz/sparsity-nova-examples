"""
Utility functions for URL extraction and HTML processing.
"""

import re
import logging
import requests
from bs4 import BeautifulSoup, Comment
from typing import List

logger = logging.getLogger(__name__)


def url_prompt(user_prompt: str) -> str:
    """
    Create a prompt to ask AI for relevant URLs.
    
    Args:
        user_prompt: The original user query.
        
    Returns:
        A prompt string for the AI.
    """
    return (
        "List me all the URLs you need to search for to get a result for the following prompt: "
        f"{user_prompt}\n"
        "Return only the URLs, one per line, no explanations. "
        "Do not include any other text in your response, and the URL should be very very specific so it can actually solve the user prompt."
        "Do not say you can't provide any URLs, just return the URLs you can find."
        "I will do visit the websites myself, so just give me the URLS. NEVER say you can't provide any URLs."
    )


def summary_prompt(user_prompt: str, url: str, html: str) -> str:
    """
    Create a prompt to ask AI to summarize HTML content.
    
    Args:
        user_prompt: The original user query.
        url: The URL of the content.
        html: The cleaned HTML content.
        
    Returns:
        A prompt string for the AI.
    """
    return (
        f"Summarize the following HTML content from {url} regarding the user prompt: '{user_prompt}'. "
        "If the content is not useful, say so.\n\n" + html[:10000]
    )


def final_summary_prompt(user_prompt: str, url_summaries: str) -> str:
    """
    Create a prompt for the final summary.
    
    Args:
        user_prompt: The original user query.
        url_summaries: Formatted summaries from all URLs.
        
    Returns:
        A prompt string for the AI.
    """
    return (
        f"Given the following summaries of content from several URLs, use the information to answer the user prompt: '{user_prompt}'. "
        "If the content is not useful, say so.\n\n" + url_summaries
    )


def extract_urls(text: str) -> List[str]:
    """
    Extract URLs from text using regex.
    
    Args:
        text: Text containing URLs.
        
    Returns:
        List of extracted URLs.
    """
    url_pattern = re.compile(r'https?://\S+')
    return url_pattern.findall(text)


def clean_html(html: str) -> str:
    """
    Clean HTML by removing scripts, styles, and comments.
    
    Args:
        html: Raw HTML content.
        
    Returns:
        Cleaned HTML with only main content.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove unwanted elements
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    
    # Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    # Return main content
    main_content = soup.find('main') or soup.find('article') or soup.body
    return str(main_content) if main_content else str(soup)


def fetch_html(url: str) -> str:
    """
    Fetch and clean HTML from a URL.
    
    Args:
        url: The URL to fetch.
        
    Returns:
        Cleaned HTML content or error message.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CoinPriceBot/1.0)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text
        processed_html = clean_html(html_content)
        return processed_html
    except Exception as e:
        error_msg = f"[ERROR] Could not fetch HTML: {e}"
        logger.warning(error_msg)
        return error_msg
