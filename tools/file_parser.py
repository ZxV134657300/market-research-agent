"""
文件解析工具模块
负责读取 PDF/TXT 文件并转换为文本，按章节分段
"""

import os
from typing import TypedDict


class DocumentChunk(TypedDict):
    """文档分段数据结构"""
    source: str       # 来源文件名
    chunk_id: int     # 分段编号
    text: str         # 分段文本内容


def parse_document(file_path: str) -> list[DocumentChunk]:
    """
    解析文档并按章节/段落分段

    Args:
        file_path: 文件路径（支持 .txt 和 .pdf）

    Returns:
        文档分段列表，每个分段包含来源、编号和文本
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".txt":
        full_text = _read_txt(file_path)
    elif ext == ".pdf":
        full_text = _read_pdf(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}（仅支持 .txt 和 .pdf）")

    chunks = _split_into_chunks(full_text, source=os.path.basename(file_path))
    return chunks


def _read_txt(file_path: str) -> str:
    """读取 TXT 文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _read_pdf(file_path: str) -> str:
    """读取 PDF 文件并提取文本"""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("需要安装 pypdf 库来解析 PDF 文件: pip install pypdf")

    reader = PdfReader(file_path)
    pages_text = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            pages_text.append(f"[第{i + 1}页] {text.strip()}")
    return "\n\n".join(pages_text)


def _split_into_chunks(text: str, source: str) -> list[DocumentChunk]:
    """
    将文本按章节/段落分段
    使用中文数字标题（一、二、三...）和空行作为分隔符
    """
    lines = text.split("\n")
    chunks: list[DocumentChunk] = []
    current_chunk_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # 检测中文数字章节标题（一、二、三、...）
        if stripped and len(stripped) > 1 and stripped[0] in "一二三四五六七八九十" and stripped[1] in "、.、":
            if current_chunk_lines:
                chunk_text = "\n".join(current_chunk_lines).strip()
                if chunk_text:
                    chunks.append(DocumentChunk(
                        source=source,
                        chunk_id=len(chunks),
                        text=chunk_text,
                    ))
                current_chunk_lines = []
        current_chunk_lines.append(line)

    # 处理最后一段
    if current_chunk_lines:
        chunk_text = "\n".join(current_chunk_lines).strip()
        if chunk_text:
            chunks.append(DocumentChunk(
                source=source,
                chunk_id=len(chunks),
                text=chunk_text,
            ))

    # 如果没有分出任何段落，将整个文本作为一段
    if not chunks:
        chunks.append(DocumentChunk(source=source, chunk_id=0, text=text))

    return chunks
