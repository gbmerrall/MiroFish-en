"""
OASIS Agent Profile Generator
Converts entities from the Zep graph into the Agent Profile format required by the OASIS simulation platform.

Optimized improvements:
1. Calls Zep retrieval function to enrich node information
2. Optimizes prompts to generate highly detailed personas
3. Distinguishes between individual entities and abstract group entities
"""

import json
import random
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from ..config import Config
from ..utils.logger import get_logger
from ..utils.graphiti_client import create_graphiti_client
from .graph_entity_reader import EntityNode

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile"""
    user_id: int
    name: str
    persona: str
    mbti: str
    country: str
    profession: str
    interested_topics: List[str]
    source_entity_uuid: str
    source_entity_type: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "persona": self.persona,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile Generator
    
    Converts entities from the Zep graph into Agent Profiles required by OASIS simulation.
    
    Optimization features:
    1. Calls Zep graph retrieval function to get richer context
    2. Generates very detailed personas (including basic information, professional experience, personality traits, social media behavior, etc.)
    3. Distinguishes between individual entities and abstract group entities
    """
    
    # MBTI type list
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # Common country list
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # Individual entity types (need to generate specific personas)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # Group/institution entity types (need to generate representative personas)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        self.graph_id = graph_id
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        Generates an OASIS Agent Profile from a Zep entity.
        
        Args:
            entity: Entity node object
            user_id: OASIS platform user ID
            use_llm: Whether to use LLM to generate persona
            
        Returns:
            OASIS Agent Profile
        """
        entity_name = entity.name
        
        # Determine entity type
        source_type = entity.get_entity_type() or "Person"
        
        # 1. Retrieve rich context (Zep retrieval)
        retrieval_results = self._retrieve_entity_context(entity)
        
        # 2. Build complete context string
        full_context = self._build_entity_context(entity)
        if retrieval_results["context"]:
            full_context += "\n\n### Additional Background (from Semantic Search)\n" + retrieval_results["context"]
            
        # 3. Generate persona
        if use_llm:
            persona_data = self._generate_persona_with_llm(entity_name, source_type, full_context)
            
            return OasisAgentProfile(
                user_id=user_id,
                name=persona_data.get("name", entity_name),
                persona=persona_data.get("persona", ""),
                mbti=persona_data.get("mbti", random.choice(self.MBTI_TYPES)),
                country=persona_data.get("country", random.choice(self.COUNTRIES)),
                profession=persona_data.get("profession", ""),
                interested_topics=persona_data.get("interested_topics", []),
                source_entity_uuid=entity.uuid,
                source_entity_type=source_type
            )
        else:
            # Fallback to random generation
            return self._generate_fallback_profile(entity, user_id)

    async def _async_retrieve_context(self, entity_name: str) -> Any:
        graphiti = create_graphiti_client()
        try:
            comprehensive_query = f"All information, activities, events, relationships, and background about {entity_name}"
            results = await graphiti.search(
                query=comprehensive_query,
                group_ids=[self.graph_id],
                num_results=30,
            )
            return results
        finally:
            await graphiti.close()

    def _retrieve_entity_context(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Retrieves rich context for an entity from the knowledge graph using semantic search.
        
        Args:
            entity: Entity node object
            
        Returns:
            Dictionary containing facts, node_summaries, and context
        """
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # graph_id must be set for search
        if not self.graph_id:
            logger.debug("Skipping Graphiti retrieval: graph_id not set")
            return results

        entity_name = entity.name
        
        try:
            search_result = asyncio.run(self._async_retrieve_context(entity_name))
            
            all_facts = set()
            for edge in getattr(search_result, 'edges', []) or []:
                if getattr(edge, 'fact', None):
                    all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            all_summaries = set()
            for node in getattr(search_result, 'nodes', []) or []:
                if getattr(node, 'summary', None):
                    all_summaries.add(node.summary)
                if getattr(node, 'name', None) and node.name != entity_name:
                    all_summaries.add(f"Related entity: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # Build comprehensive context
            context_parts = []
            if results["facts"]:
                context_parts.append("Fact information:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Related entities:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"Graphiti retrieval complete: {entity_name}, retrieved {len(results['facts'])} facts, {len(results['node_summaries'])} related nodes")
            
        except Exception as e:
            logger.warning(f"Graphiti retrieval failed ({entity_name}): {e}")
        
        return results

    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Builds the complete context information for an entity.
        
        Includes:
        1. Entity's own edge information (facts)
        2. Detailed information of associated nodes
        3. Rich information retrieved by Graphiti hybrid search
        """
        context_parts = []
        
        # 1. Add entity attribute information
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Entity Attributes\n" + "\n".join(attrs))
        
        # 2. Add related edge information (facts/relationships)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (Related Entity)")
                    else:
                        relationships.append(f"- (Related Entity) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### Related Facts and Relationships\n" + "\n".join(relationships))
        
        # 3. Add detailed information of associated nodes
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                type_label = next((l for l in node_labels if l not in ("Entity", "Node")), "Unknown")
                
                info = f"- {node_name} ({type_label})"
                if node_summary:
                    info += f": {node_summary}"
                related_info.append(info)
            
            if related_info:
                context_parts.append("### Related Entity Profiles\n" + "\n".join(related_info))
                
        return "\n\n".join(context_parts)

    def _generate_persona_with_llm(self, name: str, entity_type: str, context: str) -> Dict[str, Any]:
        """Generates detailed agent persona using LLM"""
        
        # Distinguish between individual and group entity types
        is_individual = entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
        
        system_prompt = "You are an expert in social psychology and character design. Your task is to design a highly detailed social media agent persona based on knowledge graph information."
        
        user_prompt = f"""
Based on the following knowledge graph entity information, design a social media agent persona.

Entity Name: {name}
Entity Type: {entity_type}

--- Knowledge Context ---
{context}
---

Requirements:
1. If the entity is a specific person, design a persona that matches their background.
2. If the entity is an organization (e.g., university, company), design a representative person (e.g., official spokesperson, student, employee) who reflects the organization's character.
3. The persona should be extremely detailed, including their worldview, professional experience, personality traits, social media posting style, and communication preferences.
4. Output in JSON format.

JSON schema:
{{
  "name": "Full name",
  "persona": "Detailed persona description (at least 300 words)",
  "mbti": "MBTI personality type (e.g., INTJ, ENFP)",
  "country": "Primary country of residence",
  "profession": "Specific profession or role",
  "interested_topics": ["Topic 1", "Topic 2", "Topic 3", "Topic 4", "Topic 5"]
}}
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.8
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info(f"LLM persona generation complete: {name}")
            return result
        except Exception as e:
            logger.error(f"LLM persona generation failed ({name}): {e}")
            return {}

    def _generate_fallback_profile(self, entity: EntityNode, user_id: int) -> OasisAgentProfile:
        """Generates a basic profile without LLM"""
        source_type = entity.get_entity_type() or "Person"
        return OasisAgentProfile(
            user_id=user_id,
            name=entity.name,
            persona=f"A {source_type} named {entity.name} with interest in {', '.join(entity.labels)}.",
            mbti=random.choice(self.MBTI_TYPES),
            country=random.choice(self.COUNTRIES),
            profession=source_type,
            interested_topics=entity.labels[:5],
            source_entity_uuid=entity.uuid,
            source_entity_type=source_type
        )
