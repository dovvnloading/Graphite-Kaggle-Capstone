import os
from pathlib import Path

# --- Conditional Imports for Optional Dependencies ---
# These libraries are not core requirements for the application to run, but they
# are necessary for handling specific file types (.pdf, .docx). By using a
# try-except block, the application can start even if these libraries aren't
# installed and gracefully inform the user if they attempt to use a feature
# that requires a missing dependency.

# Attempt to import pypdf for reading .pdf files.
try:
    import pypdf
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# Attempt to import python-docx for reading .docx files.
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

class FileHandler:
    """
    Handles reading and extracting text content from various file types.

    This class provides a unified interface to read plain text, PDF, and DOCX files,
    gracefully handling missing optional dependencies for PDF and DOCX processing.
    It acts as a dispatcher, selecting the appropriate reading method based on the
    file's extension. This centralizes file reading logic and makes it easy to
    extend with support for new file formats in the future.
    """

    # A set of file extensions for plain text formats that are always supported
    # without any special libraries.
    SUPPORTED_EXTENSIONS = {
        '.txt', '.md', '.py', '.json', '.html', '.css', '.js', '.csv', '.xml'
    }

    def __init__(self):
        """
        Initializes the FileHandler.

        This method dynamically expands the set of supported file extensions based on
        which optional libraries (like pypdf, python-docx) were successfully imported
        when the application started.
        """
        # Add .pdf support if the pypdf library was successfully imported.
        if PDF_AVAILABLE:
            self.SUPPORTED_EXTENSIONS.add('.pdf')
        # Add .docx support if the python-docx library was successfully imported.
        if DOCX_AVAILABLE:
            self.SUPPORTED_EXTENSIONS.add('.docx')

    def read_file(self, file_path: str) -> tuple[str | None, str | None]:
        """
        Reads a file and returns its content as a string.

        This is the main public method of the class. It validates the file path,
        determines the file type from its extension, and calls the appropriate
        private reader method. It returns a tuple where the first element is the
        file content and the second is an error message if one occurred.

        Args:
            file_path (str): The absolute path to the file to be read.

        Returns:
            tuple[str | None, str | None]: A tuple containing (content, error_message).
                                           On success, content is a string and error_message is None.
                                           On failure, content is None and error_message is a string.
        """
        path = Path(file_path)
        # First, validate that the provided path actually points to a file.
        if not path.is_file():
            return None, f"File not found: {file_path}"

        # Get the file extension in lowercase to ensure case-insensitive matching.
        ext = path.suffix.lower()

        try:
            # Dispatch to the correct reader method based on the file extension.
            if ext in ('.txt', '.md', '.py', '.json', '.html', '.css', '.js', '.csv', '.xml'):
                return self._read_text(path), None
            elif ext == '.pdf':
                # Check if the required library is available before attempting to read.
                if not PDF_AVAILABLE:
                    return None, "PDF support is not installed. Please run: pip install pypdf"
                return self._read_pdf(path), None
            elif ext == '.docx':
                # Check if the required library is available before attempting to read.
                if not DOCX_AVAILABLE:
                    return None, "Word document support is not installed. Please run: pip install python-docx"
                return self._read_docx(path), None
            else:
                # If the extension is not in our supported list, return an error.
                return None, f"Unsupported file type: {ext}"
        except Exception as e:
            # Catch any unexpected errors during file processing.
            return None, f"Error reading file '{path.name}': {str(e)}"

    def _read_text(self, path: Path) -> str:
        """
        Reads plain text files using standard file I/O.

        Args:
            path (Path): The Path object representing the file to read.

        Returns:
            str: The content of the file as a string.
        """
        # Open with utf-8 encoding and ignore errors for robustness against malformed files.
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def _read_pdf(self, path: Path) -> str:
        """
        Reads and extracts text from a PDF file using the pypdf library.

        Args:
            path (Path): The Path object representing the PDF file.

        Returns:
            str: The extracted text content, with pages joined by newlines.
        """
        content = []
        # Open the file in binary read mode ('rb') as required by pypdf.
        with open(path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            # Iterate through each page in the PDF and extract its text.
            for page in reader.pages:
                content.append(page.extract_text())
        # Join the text from all pages into a single string.
        return "\n".join(content)

    def _read_docx(self, path: Path) -> str:
        """
        Reads and extracts text from a .docx file using the python-docx library.

        Args:
            path (Path): The Path object representing the DOCX file.

        Returns:
            str: The extracted text content, with paragraphs joined by newlines.
        """
        doc = docx.Document(path)
        # Iterate through each paragraph in the document and extract its text.
        content = [para.text for para in doc.paragraphs]
        # Join the text from all paragraphs into a single string.
        return "\n".join(content)