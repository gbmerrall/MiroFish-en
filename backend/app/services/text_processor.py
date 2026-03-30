"""
Text Processing Service
"""

from typing import List
from ..utils.file_parser import FileParser, split_text_into_chunks


class TextProcessor:
    """Text Processor"""
    
    @staticmethod
    def extract_from_files(file_paths: List[str]) -> str:
        """Extracts text from multiple files"""
        return FileParser.extract_from_multiple(file_paths)
    
    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """
        Splits text into chunks
        
        Args:
            text: Original text
            chunk_size: Chunk size
            overlap: Overlap size
            
        Returns:
            List of text chunks
        """
        return split_text_into_chunks(text, chunk_size, overlap)
    
    @staticmethod
    def preprocess_text(text: str) -> str:
        """
        Preprocesses text
        - Removes redundant whitespace
        - Standardizes newlines
        
        Args:
            text: Original text
            
        Returns:
            Processed text
        """
        import re
        
        # Standardize newlines
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove consecutive blank lines (keep at most two newlines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove leading and trailing whitespace from each line
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    @staticmethod
    def get_text_stats(text: str) -> dict:
        """Gets text statistics"""
        return {
            "total_chars": len(text),
            "total_lines": text.count('\n') + 1,
            "total_words": len(text.split()),
        }
