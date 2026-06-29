"""
智能体模块 - 包含4个协作智能体
- CollectorAgent: 信息采集官
- AnalystAgent: 竞品情报官
- WriterAgent: 报告写手官
- ReviewerAgent: 质检验收官
"""

from .collector import CollectorAgent
from .analyst import AnalystAgent
from .writer import WriterAgent
from .reviewer import ReviewerAgent

__all__ = ["CollectorAgent", "AnalystAgent", "WriterAgent", "ReviewerAgent"]
