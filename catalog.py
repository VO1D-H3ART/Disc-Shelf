"""DiscShelf document catalog: only paths and filenames, never document contents."""
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = frozenset({
    '.pdf', '.docx', '.doc', '.md', '.html', '.htm',
    '.txt', '.rtf', '.odt', '.epub',
})


@dataclass(frozen=True, slots=True)
class Document:
    path: str
    name: str
    extension: str

    @property
    def title(self) -> str:
        """Preserve the exact filename stem for the book spine."""
        return Path(self.name).stem


def document_from_path(path: str) -> Document | None:
    name = Path(path).name
    extension = Path(name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        return None
    return Document(path=path, name=name, extension=extension)
