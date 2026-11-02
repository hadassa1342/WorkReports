from abc import ABC, abstractmethod

class BaseParser(ABC):
    @abstractmethod
    def parse(self, pdf_path: str):
        """פונקציית פענוח בסיסית המשותפת לכלל הפרסרים"""
        pass