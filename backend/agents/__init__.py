# Agents module
from backend.agents.parser_agent import ParserAgent
from backend.agents.title_abstract_agent import TitleAbstractKeywordsReviewerAgent
from backend.agents.structure_reviewer import StructureReviewerAgent
from backend.agents.methodology_reviewer import MethodologyReviewerAgent
from backend.agents.statistics_reviewer import StatisticsReviewerAgent
from backend.agents.figures_tables_agent import FiguresTablesReviewerAgent
from backend.agents.results_reviewer import ResultsReviewerAgent
from backend.agents.discussion_conclusions_agent import DiscussionConclusionsReviewerAgent
from backend.agents.writing_reviewer import WritingReviewerAgent
from backend.agents.references_reviewer import ReferencesReviewerAgent
from backend.agents.ethics_limitations_reviewer import EthicsLimitationsReviewerAgent
from backend.agents.meta_reviewer import MetaReviewerAgent

__all__ = [
    "ParserAgent",
    "TitleAbstractKeywordsReviewerAgent",
    "StructureReviewerAgent",
    "MethodologyReviewerAgent",
    "StatisticsReviewerAgent",
    "FiguresTablesReviewerAgent",
    "ResultsReviewerAgent",
    "DiscussionConclusionsReviewerAgent",
    "WritingReviewerAgent",
    "ReferencesReviewerAgent",
    "EthicsLimitationsReviewerAgent",
    "MetaReviewerAgent",
]
