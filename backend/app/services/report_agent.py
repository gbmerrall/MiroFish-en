"""
Report Agent Service
ReACT-mode simulation report generation using LangChain + Zep

Features:
1. Generates reports based on simulation requirements and Zep graph information.
2. Plans outline structure first, then generates section by section.
3. Each section uses ReACT multi-round thinking and reflection mode.
4. Supports dialogue with user, autonomously calling retrieval tools during chat.
"""

import os
import json
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Report Agent Detailed Log Recorder
    
    Generates agent_log.jsonl in the report folder, recording every detailed step.
    Each line is a complete JSON object containing timestamp, action type, detailed content, etc.
    """
    
    def __init__(self, report_id: str):
        """
        Initializes the log recorder
        
        Args:
            report_id: Report ID, used to determine log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensures the directory for the log file exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Gets elapsed time since start (seconds)"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Records a log entry
        
        Args:
            action: Action type, e.g., 'start', 'tool_call', 'llm_response', 'section_complete', etc.
            stage: Current stage, e.g., 'planning', 'generating', 'completed'
            details: Detailed content dictionary, not truncated
            section_title: Current section title (optional)
            section_index: Current section index (optional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # Append to JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Records the start of report generation"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started"
            }
        )
    
    def log_planning_start(self):
        """Records the start of outline planning"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Starting report outline planning"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Records context information retrieved during planning"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Retrieving simulation context information",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Records completion of outline planning"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Outline planning complete",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Records the start of section generation"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Starting section generation: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Records ReACT thought process"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT round {iteration} thinking"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Records tool call"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Calling tool: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Records tool call result (full content, not truncated)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Full result, not truncated
                "result_length": len(result),
                "message": f"Tool {tool_name} returned result"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Records LLM response (full content, not truncated)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Full response, not truncated
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (Tool call: {has_tool_calls}, Final Answer: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Records completion of section content generation (content only, not entire section)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Full content, not truncated
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Section {section_title} content generation complete"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Records full completion of section generation.

        Frontend should listen to this log to determine if a section is truly complete and get full content.
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Section {section_title} generation complete"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Records completion of report generation"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation complete"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Records an error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"An error occurred: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent Console Log Recorder
    
    Writes console-style logs (INFO, WARNING, etc.) into console_log.txt in the report folder.
    These are plain text console outputs, different from the structured agent_log.jsonl.
    """
    
    def __init__(self, report_id: str):
        """
        Initializes the console log recorder
        
        Args:
            report_id: Report ID, used to determine log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Ensures the directory for the log file exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Sets up file handler to write logs to file simultaneously"""
        import logging
        
        # Create file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Use concise format same as console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Attach to report_agent related loggers
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Avoid duplicate attachments
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Closes file handler and removes from loggers"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Ensures file handler is closed on destruction"""
        self.close()


class ReportStatus(str, Enum):
    """Report Status"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Report Section"""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """Converts to Markdown format"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Report Outline"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Converts to Markdown format"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Complete Report"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Prompt Template Constants
# ═══════════════════════════════════════════════════════════════

# ── Tool Descriptions ──

TOOL_DESC_INSIGHT_FORGE = """\
[Deep Insight Retrieval - Powerful Retrieval Tool]
This is our powerful retrieval function designed for deep analysis. It will:
1. Automatically decompose your question into multiple sub-questions.
2. Retrieve information from the simulation graph across multiple dimensions.
3. Integrate results from semantic search, entity analysis, and relationship chain tracking.
4. Return the most comprehensive and deep retrieval content.

[Usage Scenarios]
- Need deep analysis of a certain topic.
- Need to understand multiple aspects of an event.
- Need rich material to support report sections.

[Return Content]
- Original relevant facts (can be cited directly).
- Core entity insights.
- Relationship chain analysis."""

TOOL_DESC_PANORAMA_SEARCH = """\
[Panorama Search - Get Full View]
This tool is used to get the complete overview of simulation results, especially suitable for understanding event evolution. It will:
1. Retrieve all relevant nodes and relationships.
2. Distinguish between currently valid facts and historical/expired facts.
3. Help you understand how public opinion evolved.

[Usage Scenarios]
- Need to understand the full development process of an event.
- Need to compare public opinion changes across different stages.
- Need to obtain comprehensive entity and relationship information.

[Return Content]
- Currently valid facts (latest simulation results).
- Historical/expired facts (evolution records).
- All involved entities."""

TOOL_DESC_QUICK_SEARCH = """\
[Quick Search - Fast Retrieval]
Lightweight fast retrieval tool, suitable for simple and direct information queries.

[Usage Scenarios]
- Need to quickly find specific information.
- Need to verify a certain fact.
- Simple information retrieval.

[Return Content]
- List of facts most relevant to the query."""

TOOL_DESC_INTERVIEW_AGENTS = """\
[Deep Interview - Real Agent Interview (Dual-platform)]
Calls the interview API of the OASIS simulation environment to conduct real interviews with running simulation Agents!
This is not an LLM simulation, but a call to the actual interview interface to get original answers from simulation Agents.
By default, it interviews on both Twitter and Reddit platforms simultaneously to get more comprehensive views.

Workflow:
1. Automatically reads persona files to understand all simulation Agents.
2. Smartly selects Agents most relevant to the interview topic (e.g., students, media, officials, etc.).
3. Automatically generates interview questions.
4. Calls /api/simulation/interview/batch interface for real interviews on dual platforms.
5. Integrates all interview results to provide multi-perspective analysis.

[Usage Scenarios]
- Need to understand event perspectives from different roles (What do students think? What does the media say? What do officials state?).
- Need to collect opinions and stances from multiple parties.
- Need to obtain real answers from simulation Agents (from the OASIS simulation environment).
- Want to make the report more vivid, including "Interview Records".

[Return Content]
- Identity information of interviewed Agents.
- Interview answers from each Agent on Twitter and Reddit platforms.
- Key quotes (can be cited directly).
- Interview summary and viewpoint comparison.

[IMPORTANT] Requires the OASIS simulation environment to be running to use this feature!"""

# ── Outline Planning Prompt ──

PLAN_SYSTEM_PROMPT = """\
You are an expert in writing "Future Prediction Reports", possessing a "God's eye view" of the simulated world - you can insight the behavior, speech, and interactions of every Agent in the simulation.

[Core Concept]
We have built a simulated world and injected specific "simulation requirements" as variables. The evolution results of the simulated world are predictions of what might happen in the future. You are not observing "experimental data", but a "preview of the future".

[Your Task]
Write a "Future Prediction Report" answering:
1. What happened in the future under the conditions we set?
2. How did various types of Agents (groups) react and act?
3. What noteworthy future trends and risks does this simulation reveal?

[Report Positioning]
- ✅ This is a simulation-based future prediction report, revealing "if this happens, what will the future be like".
- ✅ Focus on predicted results: event direction, group reactions, emergent phenomena, potential risks.
- ✅ Agent speech and behavior in the simulated world are predictions of future human behavior.
- ❌ Not an analysis of the current status of the real world.
- ❌ Not a generic public opinion summary.

[Section Count Limit]
- Minimum 2 sections, maximum 5 sections.
- No sub-sections needed; each section writes complete content directly.
- Content should be concise, focusing on core prediction findings.
- Section structure is designed by you based on prediction results.

Please output the report outline in JSON format as follows:
{
    "title": "Report Title",
    "summary": "Report Summary (one sentence summarizing core prediction findings)",
    "sections": [
        {
            "title": "Section Title",
            "description": "Section Content Description"
        }
    ]
}

Note: sections array must have 2 to 5 elements!"""

PLAN_USER_PROMPT_TEMPLATE = """\
[Prediction Scenario Setting]
Variables injected into the simulated world (simulation requirements): {simulation_requirement}

[Simulated World Scale]
- Number of entities participating: {total_nodes}
- Number of relationships generated: {total_edges}
- Entity type distribution: {entity_types}
- Number of active Agents: {total_entities}

[Sample Future Facts Predicted by Simulation]
{related_facts_json}

Please examine this future preview with a "God's eye view":
1. What state does the future present under our set conditions?
2. How do various groups of people (Agents) react and act?
3. What noteworthy future trends does this simulation reveal?

Design the most appropriate report section structure based on the predicted results.

[Reminder] Number of sections: minimum 2, maximum 5. Content should be concise and focused on core prediction findings."""

# ── Section Generation Prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert in writing "Future Prediction Reports", currently writing a section of a report.

Report Title: {report_title}
Report Summary: {report_summary}
Prediction Scenario (Simulation Requirements): {simulation_requirement}

Current Section to Write: {section_title}

═══════════════════════════════════════════════════════════════
[Core Concept]
═══════════════════════════════════════════════════════════════

The simulated world is a preview of the future. We injected specific conditions (simulation requirements) into the simulated world.
Agent behaviors and interactions in the simulation are predictions of future human behavior.

Your task is to:
- Reveal what happened in the future under set conditions.
- Predict how various groups of people (Agents) reacted and acted.
- Discover noteworthy future trends, risks, and opportunities.

❌ Do not write as an analysis of the current status of the real world.
✅ Focus on "what the future will be like" - simulation results are the predicted future.

═══════════════════════════════════════════════════════════════
[Most Important Rules - MUST BE FOLLOWED]
═══════════════════════════════════════════════════════════════

1. [MUST CALL TOOLS TO OBSERVE THE SIMULATED WORLD]
   - You are observing a preview of the future with a "God's eye view".
   - All content must come from events and Agent speech/behavior occurring in the simulated world.
   - Forbidden to use your own knowledge to write report content.
   - Call tools at least 3 times (max 5 times) per section to observe the simulated world, which represents the future.

2. [MUST CITE AGENT'S ORIGINAL SPEECH AND BEHAVIOR]
   - Agent speech and behavior are predictions of future human behavior.
   - Use citation format in the report to show these predictions, for example:
     > "Certain groups of people will state: Original content..."
   - These citations are core evidence of simulation predictions.

3. [LANGUAGE CONSISTENCY - CITED CONTENT MUST BE TRANSLATED TO REPORT LANGUAGE]
   - Tool-returned content might contain English or mixed expressions.
   - If simulation requirements and materials are in Chinese, the report must be written entirely in Chinese.
   - When citing English or mixed content returned by tools, you must translate it into fluent target language before writing into the report.
   - Maintain original meaning during translation, ensuring natural and smooth expression.
   - This rule applies to both main text and citation blocks (> format).

4. [FAITHFULLY PRESENT PREDICTED RESULTS]
   - Report content must reflect simulation results representing the future in the simulated world.
   - Do not add information not present in the simulation.
   - if information is insufficient in some aspect, state it as it is.

═══════════════════════════════════════════════════════════════
[⚠️ Format Specifications - EXTREMELY IMPORTANT!]
═══════════════════════════════════════════════════════════════

[One Section = Minimum Unit of Content]
- Each section is the minimum unit of report chunking.
- ❌ Forbidden to use any Markdown headings (#, ##, ###, ####, etc.) inside the section.
- ❌ Forbidden to add the main section title at the beginning of the content.
- ✅ Section titles are added automatically by the system; you only need to write pure text content.
- ✅ Use **bold**, paragraph separators, citations, and lists to organize content, but do not use headings.

[Correct Example]
```
This section analyzes the public opinion dissemination trend of the event. Through deep analysis of simulation data, we found...

**Initial Outbreak Stage**

Twitter, as the primary scene of public opinion, assumed the core function of initial information release:

> "Twitter contributed 68% of the initial volume..."

**Emotion Amplification Stage**

Reddit platform further amplified event impact:

- Strong visual impact
- High emotional resonance
```

[Incorrect Example]
```
## Executive Summary          ← Incorrect! Do not add any headings
### 1. Initial Stage          ← Incorrect! Do not use ### for sub-sections
#### 1.1 Detailed Analysis    ← Incorrect! Do not use #### for sub-segments

This section analyzes...
```

═══════════════════════════════════════════════════════════════
[Available Retrieval Tools] (Call 3-5 times per section)
═══════════════════════════════════════════════════════════════

{tools_description}

[Tool Usage Suggestions - Please mix different tools, do not use only one]
- insight_forge: Deep insight analysis, automatically decomposes questions and retrieves facts and relationships across multiple dimensions.
- panorama_search: Wide-angle panoramic search, understand the full picture, timeline, and evolution process of the event.
- quick_search: Quickly verify a specific information point.
- interview_agents: Interview simulation Agents to get first-person viewpoints and real reactions from different roles.

═══════════════════════════════════════════════════════════════
[Workflow]
═══════════════════════════════════════════════════════════════

Each time you reply, you can only do one of the following two things (cannot do both simultaneously):

Option A - Call Tool:
Output your thought, then call a tool using the following format:
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>
The system will execute the tool and return the result to you. You do not need to and cannot write tool return results yourself.

Option B - Output Final Content:
When you have obtained enough information via tools, output section content starting with "Final Answer:".

⚠️ Strictly Forbidden:
- Forbidden to include both tool call and Final Answer in a single reply.
- Forbidden to fabricate tool return results (Observation); all tool results are injected by the system.
- Maximum one tool call per reply.

═══════════════════════════════════════════════════════════════
[Section Content Requirements]
═══════════════════════════════════════════════════════════════

1. Content must be based on simulation data retrieved by tools.
2. Heavily cite original texts to demonstrate simulation effects.
3. Use Markdown format (but forbid headings):
   - Use **bold text** to mark key points (replacing sub-headings).
   - Use lists (- or 1.2.3.) to organize key points.
   - Use blank lines to separate different paragraphs.
   - ❌ Forbidden to use #, ##, ###, #### or any heading syntax.
4. [Citation Format Specification - MUST BE SEPARATE PARAGRAPH]
   Citations must be separate paragraphs with a blank line before and after, not mixed within paragraphs:

   ✅ Correct format:
   ```
   The university's response was considered to lack substance.

   > "The university's response pattern appeared rigid and slow in the rapidly changing social media environment."

   This evaluation reflects widespread public dissatisfaction.
   ```

   ❌ Incorrect format:
   ```
   The university's response was considered to lack substance. > "The university's response pattern..." This evaluation reflects...
   ```
5. Maintain logical consistency with other sections.
6. [Avoid Repetition] Carefully read the completed section content below and do not repeat the same information.
7. [Again] Do not add any headings! Use **bold** instead of sub-headings."""

SECTION_USER_PROMPT_TEMPLATE = """\
Completed section content (please read carefully to avoid repetition):
{previous_content}

═══════════════════════════════════════════════════════════════
[Current Task] Writing Section: {section_title}
═══════════════════════════════════════════════════════════════

[Important Reminders]
1. Read the completed sections above carefully to avoid repeating the same content!
2. Must call tools to get simulation data before starting.
3. Please mix different tools, do not use only one.
4. Report content must come from retrieval results, do not use your own knowledge.

[⚠️ Format Warning - MUST BE FOLLOWED]
- ❌ Do not write any headings (#, ##, ###, #### are all not allowed).
- ❌ Do not write "{section_title}" as the beginning.
- ✅ Section titles are added automatically by the system.
- ✅ Write text directly, using **bold** instead of sub-headings.

Please start:
1. First think (Thought) about what information this section needs.
2. Then call tool (Action) to get simulation data.
3. Output Final Answer (pure text, no headings) after collecting enough information."""

# ── ReACT Loop Message Templates ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (Retrieval Results):

═══ Tool {tool_name} Returns ═══
{result}

═══════════════════════════════════════════════════════════════
Called tools {tool_calls_count}/{max_tool_calls} times (Used: {used_tools_str}) {unused_hint}
- If information is sufficient: output section content starting with "Final Answer:" (must cite original text above).
- If more information is needed: call a tool to continue retrieval.
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Attention] You have only called tools {tool_calls_count} times, at least {min_tool_calls} are required."
    "Please call tools again to get more simulation data, then output Final Answer. {unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Currently only called tools {tool_calls_count} times, at least {min_tool_calls} are required."
    "Please call tools to get simulation data. {unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Tool call limit reached ({tool_calls_count}/{max_tool_calls}), no more tool calls allowed."
    'Please output section content starting with "Final Answer:" immediately based on obtained information.'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 You haven't used: {unused_list}. Suggest trying different tools to get multi-perspective info."

REACT_FORCE_FINAL_MSG = "Tool call limit reached. Please output Final Answer: and generate section content directly."

# ── Chat Prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
You are a concise and efficient simulation prediction assistant.

[Background]
Prediction conditions: {simulation_requirement}

[Generated Analysis Report]
{report_content}

[Rules]
1. Prioritize answering based on the report content above.
2. Answer questions directly, avoid long discursive thinking.
3. Call tools to retrieve more data only when report content is insufficient to answer.
4. Answers should be concise, clear, and organized.

[Available Tools] (Use only when necessary, max 1-2 calls)
{tools_description}

[Tool Call Format]
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>

[Answer Style]
- Concise and direct, no long windedness.
- Use > format to cite key content.
- Give conclusion first, then explain reasons."""

CHAT_OBSERVATION_SUFFIX = "\n\nPlease answer the question concisely."


# ═══════════════════════════════════════════════════════════════
# ReportAgent Main Class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Simulation Report Generation Agent

    Uses ReACT (Reasoning + Acting) mode:
    1. Planning Stage: Analyzes simulation requirements, plans report outline structure.
    2. Generation Stage: Generates content section by section, each section can call tools multiple times.
    3. Reflection Stage: Checks content completeness and accuracy.
    """
    
    # Max tool calls per section
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # Max reflection rounds
    MAX_REFLECTION_ROUNDS = 3
    
    # Max tool calls per chat
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        Initializes Report Agent
        
        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description
            llm_client: LLM client (optional)
            zep_tools: Zep tools service (optional)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        
        # Tool definitions
        self.tools = self._define_tools()
        
        # Log recorder (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Console log recorder (initialized in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent initialization complete: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Defines available tools"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "Question or topic you want to analyze deeply",
                    "report_context": "Current report section context (optional, helps generate more precise sub-questions)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query for relevance sorting",
                    "include_expired": "Whether to include expired/historical content (default True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string",
                    "limit": "Number of results to return (optional, default 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement description (e.g., 'Understand students\' views on the dormitory formaldehyde incident')",
                    "max_agents": "Max number of Agents to interview (optional, default 5, max 10)"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Executes tool call
        
        Args:
            tool_name: Tool name
            parameters: Tool parameters
            report_context: Report context (used for InsightForge)
            
        Returns:
            Tool execution result (text format)
        """
        logger.info(f"Executing tool: {tool_name}, Parameters: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Breadth Search - Get full view
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Simple Search - Fast retrieval
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Deep Interview - Calls actual OASIS interview API to get simulation Agent answers (dual-platform)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== Backward compatible old tools (internally redirected to new tools) ==========
            
            elif tool_name == "search_graph":
                # Redirect to quick_search
                logger.info("search_graph redirected to quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Redirect to insight_forge as it's more powerful
                logger.info("get_simulation_context redirected to insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Unknown tool: {tool_name}. Please use one of: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, Error: {str(e)}")
            return f"Tool execution failed: {str(e)}"
    
    # Valid tool names set for bare JSON parsing validation
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parses tool calls from LLM response

        Supported formats (in priority):
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. Bare JSON (response as a whole or a single line is a tool call JSON)
        """
        tool_calls = []

        # Format 1: XML style (standard format)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Format 2: Fallback - LLM directly outputs bare JSON (not wrapped in <tool_call> tags)
        # Attempted only when Format 1 fails to avoid mismatches in main text
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # Response might contain thought text + bare JSON, attempt to extract the last JSON object
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Validates if parsed JSON is a valid tool call"""
        # Supports {"name": ..., "parameters": ...} and {"tool": ..., "params": ...} keys
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Uniform keys to name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """Generates tool description text"""
        desc_parts = ["Available Tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Plans report outline
        
        Uses LLM to analyze simulation requirements and plan report directory structure.
        
        Args:
            progress_callback: Progress callback function
            
        Returns:
            ReportOutline: Report outline
        """
        logger.info("Starting report outline planning...")
        
        if progress_callback:
            progress_callback("planning", 0, "Analyzing simulation requirements...")
        
        # Get simulation context first
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "Generating report outline...")
        
        system_prompt = PLAN_SYSTEM_PROMPT
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Parsing outline structure...")
            
            # Parse outline
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "Simulation Analysis Report"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "Outline planning complete")
            
            logger.info(f"Outline planning complete: {len(sections)} sections")
            return outline
            
        except Exception as e:
            logger.error(f"Outline planning failed: {str(e)}")
            # Return default outline (3 sections) as fallback
            return ReportOutline(
                title="Future Prediction Report",
                summary="Analysis of future trends and risks based on simulation predictions",
                sections=[
                    ReportSection(title="Prediction Scenario and Core Findings"),
                    ReportSection(title="Population Behavior Prediction Analysis"),
                    ReportSection(title="Trends Outlook and Risk Reminders")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Generates single section content using ReACT mode
        
        ReACT loop:
        1. Thought - Analyze what information is needed.
        2. Action - Call tool to get information.
        3. Observation - Analyze tool return result.
        4. Repeat until enough info or max attempts reached.
        5. Final Answer - Generate section content.
        
        Args:
            section: Section to generate
            outline: Full outline
            previous_sections: Contents of previous sections (for continuity)
            progress_callback: Progress callback
            section_index: Section index (for logging)
            
        Returns:
            Section content (Markdown format)
        """
        logger.info(f"ReACT generating section: {section.title}")
        
        # Record section start log
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # Build user prompt - pass max 4000 characters for each completed section
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT Loop
        tool_calls_count = 0
        max_iterations = 5
        min_tool_calls = 3
        conflict_retries = 0
        used_tools = set()
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # Report context for sub-query generation in InsightForge
        report_context = f"Section Title: {section.title}\nSimulation Requirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Deep retrieving and writing ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # Call LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Check if LLM return is None
            if response is None:
                logger.warning(f"Section {section.title} iteration {iteration + 1}: LLM returned None")
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(Empty response)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                break

            logger.debug(f"LLM response: {response[:200]}...")

            # Parse once, reuse result
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Conflict Handling: LLM outputs both tool call and Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Section {section.title} round {iteration+1}: "
                    f"LLM output both tool call and Final Answer (Conflict #{conflict_retries})"
                )

                if conflict_retries <= 2:
                    # Discard response and ask LLM to retry
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Format Error] You included both tool call and Final Answer in a single reply, which is not allowed.\n"
                            "Each reply must do only one of:\n"
                            "- Call a tool (output a <tool_call> block, do not write Final Answer)\n"
                            "- Output final content (start with 'Final Answer:', do not include <tool_call>)\n"
                            "Please reply again doing only one."
                        ),
                    })
                    continue
                else:
                    # Downgrade: truncate to first tool call and force execution
                    logger.warning(
                        f"Section {section.title}: {conflict_retries} consecutive conflicts, "
                        "downgrading to executing first truncated tool call"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Record LLM response log
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Case 1: LLM outputs Final Answer ──
            if has_final_answer:
                # Insufficient tool calls, reject and ask for more
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(These tools haven't been used, suggest trying them: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Normal completion
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Section {section.title} generation complete (Tool calls: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Case 2: LLM attempts tool call ──
            if has_tool_calls:
                # Tool limit reached -> ask for Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Execute only the first tool call
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM attempted {len(tool_calls)} tool calls, executing only the first: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Build unused tools hint
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Case 3: Neither tool call nor Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Insufficient tool calls, suggest unused ones
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools haven't been used, suggest trying them: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Tool calls sufficient, adopt LLM output as final content even if prefix missing
            logger.info(f"Section {section.title} missing 'Final Answer:' prefix, adopting LLM output as final content (Tool calls: {tool_calls_count})")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Max iterations reached, force content generation
        logger.warning(f"Section {section.title} reached max iterations, forcing generation")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Check if LLM returns None during forced completion
        if response is None:
            logger.error(f"Section {section.title} forced completion returned None, using default error message")
            final_answer = "(Generation failed for this section: LLM returned empty response, please try again later)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Record section content completion log
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generates full report (streaming output section by section)
        
        Each section is saved to the folder immediately upon completion.
        File structure:
        reports/{report_id}/
            meta.json       - Report meta information
            outline.json    - Report outline
            progress.json   - Generation progress
            section_01.md   - Section 1
            section_02.md   - Section 2
            ...
            full_report.md  - Complete report
        
        Args:
            progress_callback: Progress callback function (stage, progress, message)
            report_id: Report ID (optional, auto-generated if missing)
            
        Returns:
            Report: Complete report
        """
        import uuid
        
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        completed_section_titles = []
        
        try:
            # Initialization: create report folder and save initial state
            ReportManager._ensure_report_folder(report_id)
            
            # Initialize structured log recorder
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Initialize console log recorder
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Initializing report...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Stage 1: Planning Outline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Starting report outline planning...",
                completed_sections=[]
            )
            
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Starting report outline planning...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # Save outline to file
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Outline planning complete with {len(outline.sections)} sections",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"Outline saved to file: {report_id}/outline.json")
            
            # Stage 2: Section-by-section Generation
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"Generating section: {section.title} ({section_num}/{total_sections})"
                    )
                
                # Generate main section content
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Save section
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Record section full complete log
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Section saved: {report_id}/section_{section_num:02d}.md")
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Section {section.title} complete",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Stage 3: Assembling Full Report
            if progress_callback:
                progress_callback("generating", 95, "Assembling complete report...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "Assembling complete report...",
                completed_sections=completed_section_titles
            )
            
            # Assemble full report
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Calculate total duration
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # Record report complete log
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Save final report
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Report generation complete",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "Report generation complete")
            
            logger.info(f"Report generation complete: {report_id}")
            
            # Close console log recorder
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # Save failure state
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Report generation failed: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass
            
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Dialogues with Report Agent
        
        Agent can autonomously call retrieval tools during dialogue to answer questions.
        
        Args:
            message: User message
            chat_history: Dialogue history
            
        Returns:
            {
                "response": "Agent reply",
                "tool_calls": [List of tools called],
                "sources": [Information sources]
            }
        """
        logger.info(f"Report Agent dialogue: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # Get generated report content
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limit report length to avoid context being too long
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Report content truncated] ..."
        except Exception as e:
            logger.warning(f"Failed to get report content: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(No report yet)",
            tools_description=self._get_tools_description(),
        )

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add history
        for h in chat_history[-10:]:
            messages.append(h)
        
        # Add user message
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT Loop (simplified)
        tool_calls_made = []
        max_iterations = 2
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Parse tool calls
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # No tool call, return response directly
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Execute tool call (limit quantity)
            tool_results = []
            for call in tool_calls[:1]:  # Max 1 tool call per round
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limit result length
                })
                tool_calls_made.append(call)
            
            # Add result to messages
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} Result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Final response
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Clean response
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Report Manager
    
    Responsible for persistent storage and retrieval of reports.
    
    File structure (sectioned output):
    reports/
      {report_id}/
        meta.json          - Report meta info and status
        outline.json       - Report outline
        progress.json      - Generation progress
        section_01.md      - Section 1
        section_02.md      - Section 2
        ...
        full_report.md     - Complete report
    """
    
    # Report storage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Ensures report root directory exists"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Gets report folder path"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Ensures report folder exists and returns path"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Gets report meta info file path"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Gets full report Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Gets outline file path"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Gets progress file path"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Gets section Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Gets Agent log file path"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Gets console log file path"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Gets console log content
        
        This is console output log (INFO, WARNING, etc.) during report generation,
        different from structured agent_log.jsonl.
        
        Args:
            report_id: Report ID
            from_line: Line number to start reading from (for incremental retrieval, 0 is from start)
            
        Returns:
            {
                "logs": [List of log lines],
                "total_lines": Total lines,
                "from_line": Starting line number,
                "has_more": Whether there are more logs
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Retain original log lines, remove trailing newline
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Already read to the end
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Gets full console log (retrieves all at once)
        
        Args:
            report_id: Report ID
            
        Returns:
            List of log lines
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Gets Agent log content
        
        Args:
            report_id: Report ID
            from_line: Line number to start reading from (for incremental retrieval, 0 is from start)
            
        Returns:
            {
                "logs": [List of log entries],
                "total_lines": Total lines,
                "from_line": Starting line number,
                "has_more": Whether there are more logs
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Skip lines that fail to parse
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Already read to the end
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Gets full Agent log (retrieves all at once)
        
        Args:
            report_id: Report ID
            
        Returns:
            List of log entries
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Saves report outline
        
        Called immediately after planning stage completion.
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Outline saved: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Saves a single section.

        Called immediately after each section is generated, achieving sectioned output.

        Args:
            report_id: Report ID
            section_index: Section index (starting from 1)
            section: Section object

        Returns:
            Saved file path
        """
        cls._ensure_report_folder(report_id)

        # Build section Markdown content - clean potential duplicate titles
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Save file
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Section saved: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Cleans section content.
        
        1. Removes Markdown title lines at start duplicate with section title.
        2. Converts all ### and lower level headings to bold text.
        
        Args:
            content: Original content
            section_title: Section title
            
        Returns:
            Cleaned content
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check for Markdown heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                # level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Check for duplicate with section title (skip if within first 5 lines)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Convert all headings level (#, ##, ###, ####, etc.) to bold
                # Content should have no headings as section headings are system-added
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Add empty line
                continue
            
            # If previous line was a skipped heading and current line is empty, skip it too
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Remove leading empty lines
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Remove leading separators
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # and empty lines after separators
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Updates report generation progress.
        
        Frontend can get real-time progress by reading progress.json.
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Gets report generation progress"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Gets list of already generated sections.
        
        Returns info of all saved section files.
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse section index from filename
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assembles full report.
        
        Assembles full report from saved section files and performs title cleaning.
        """
        # folder = cls._get_report_folder(report_id)
        
        # Build report header
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += "---\n\n"
        
        # Read all section files in order
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # Post-processing: clean title issues in the whole report
        md_content = cls._post_process_report(md_content, outline)
        
        # Save full report
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Full report assembled: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-processes report content.
        
        1. Removes duplicate titles.
        2. Retains report main heading (#) and section headings (##), converts others (###, ####, etc.) to bold.
        3. Cleans redundant empty lines and separators.
        
        Args:
            content: Original report content
            outline: Report outline
            
        Returns:
            Processed content
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Collect all section titles from outline
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check for heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Check for duplicate title (same content within last 5 lines)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Skip duplicate title and following empty lines
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Heading hierarchy handling:
                # - # (level=1) Retain report main title
                # - ## (level=2) Retain section headings
                # - ### and below (level>=3) Convert to bold text
                
                if level == 1:
                    if title == outline.title:
                        # Retain report main title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Section title incorrectly used #, fix to ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Convert other level 1 headings to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Retain section heading
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Non-section level 2 headings to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # Level 3 and below to bold
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Skip separator immediately after heading
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Retain only one empty line after heading
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Clean consecutive multiple blank lines (keep at most 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Saves report meta info and full report"""
        cls._ensure_report_folder(report.report_id)
        
        # Save meta info JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Save outline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # Save full Markdown report
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"Report saved: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Gets report"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Backward compatibility: check files stored directly in reports directory
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Rebuild Report object
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # If markdown_content is empty, attempt to read from full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Gets report by simulation ID"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Backward compatibility: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """Lists reports"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Backward compatibility: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # Sort by creation time descending
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Deletes report (entire folder)"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # New format: delete entire folder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Report folder deleted: {report_id}")
            return True
        
        # Backward compatibility: delete individual files
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
