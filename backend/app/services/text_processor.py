"""
Text Processing Utilities
Provides text cleaning, chunking, and preprocessing functions.
"""

import re
from typing import List


class TextProcessor:
    """
    Text processing utilities
    """
    
    @staticmethod
    def clean_text(text: str) -> str:
        """
        Cleans text:
        - Standardize newlines
        - Remove redundant whitespace
        
        Args:
            text: Original text
            
        Returns:
            Processed text
        """
        if not text:
            return ""
            
        # Standardize newlines
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove consecutive empty lines (keep at most two newlines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove redundant spaces on each line
        lines = [line.strip() for line in text.split('\n')]
        
        # Merge lines
        return '\n'.join(lines)
    
    @staticmethod
    def split_text(
        text: str, 
        chunk_size: int = 500, 
        chunk_overlap: int = 50
    ) -> List[str]:
        """
        Splits text into chunks, using sentence boundaries where possible.
        
        Args:
            text: Input text
            chunk_size: Target size of each chunk
            chunk_overlap: Number of characters to overlap between chunks
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
            
        if len(text) <= chunk_size:
            return [text.strip()] if text.strip() else []
            
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # If not the end, try to find a natural break point (newline or punctuation)
            if end < len(text):
                # Search for break point in the overlap area
                search_area = text[end - chunk_overlap : end + chunk_overlap]
                
                # Priority break points
                break_points = ['\n\n', '\n', '. ', '。', '! ', '！', '? ', '？']
                
                found_break = False
                for bp in break_points:
                    idx = search_area.rfind(bp)
                    if idx != -1:
                        end = (end - chunk_overlap) + idx + len(bp)
                        found_break = True
                        break
                
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
                
            # Move start to next chunk, accounting for overlap
            start = max(start + 1, end - chunk_overlap)
            
            # Guard against infinite loop
            if start >= len(text):
                break
                
        return chunks
