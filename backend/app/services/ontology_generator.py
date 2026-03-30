"""
Ontology Generation Service
Interface 1: Analyzes text content and generates entity and relationship type definitions suitable for social simulation.
"""

from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient


# System prompt for ontology generation
ONTOLOGY_SYSTEM_PROMPT = """You are a professional knowledge graph ontology design expert. Your task is to analyze given text content and simulation requirements to design entity and relationship types suitable for **social media public opinion simulation**.

**IMPORTANT: You must output valid JSON format data. Do not output any other content.**

## Core Task Background

We are building a **social media public opinion simulation system**. In this system:
- Each entity is an "account" or "subject" that can voice opinions, interact, and spread information on social media.
- Entities will influence each other, repost, comment, and respond.
- We need to simulate the reactions of all parties and the path of information dissemination in public opinion events.

Therefore, **entities must be subjects that exist in reality and can voice opinions and interact on social media**:

**CAN BE**:
- Specific individuals (public figures, parties involved, opinion leaders, experts/scholars, ordinary people)
- Companies, enterprises (including their official accounts)
- Organizations (universities, associations, NGOs, trade unions, etc.)
- Government departments, regulatory agencies
- Media organizations (newspapers, TV stations, self-media, websites)
- Social media platforms themselves
- Representatives of specific groups (e.g., alumni associations, fan clubs, rights groups, etc.)

**CANNOT BE**:
- Abstract concepts (e.g., "public opinion", "emotion", "trend")
- Themes/Topics (e.g., "academic integrity", "education reform")
- Viewpoints/Attitudes (e.g., "supporters", "opponents")

## Output Format

Please output in JSON format with the following structure:

```json
{
    "entity_types": [
        {
            "name": "Entity type name (English, PascalCase)",
            "description": "Short description (English, max 100 characters)",
            "attributes": [
                {
                    "name": "Attribute name (English, snake_case)",
                    "type": "text",
                    "description": "Attribute description"
                }
            ],
            "examples": ["Example entity 1", "Example entity 2"]
        }
    ],
    "edge_types": [
        {
            "name": "Relationship type name (English, UPPER_SNAKE_CASE)",
            "description": "Short description (English, max 100 characters)",
            "source_targets": [
                {"source": "Source entity type", "target": "Target entity type"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Brief analysis description of the text content (English)"
}
```

## Design Guidelines (EXTREMELY IMPORTANT!)

### 1. Entity Type Design - Must strictly comply

**Quantity Requirement: Must have EXACTLY 10 entity types**

**Hierarchy Requirement (Must include both specific and fallback types)**:

Your 10 entity types must include the following hierarchy:

A. **Fallback Types (Must be included, place as the last 2 in the list)**:
   - `Person`: Fallback type for any individual human. Used when a person doesn't fit into other more specific person types.
   - `Organization`: Fallback type for any organization. Used when an organization doesn't fit into other more specific organization types.

B. **Specific Types (8 types, designed based on text content)**:
   - Design more specific types for the main characters appearing in the text.
   - Example: If the text involves academic events, you could have `Student`, `Professor`, `University`.
   - Example: If the text involves business events, you could have `Company`, `CEO`, `Employee`.

**Why fallback types are needed**:
- Various people like "primary school teacher", "passerby A", "a certain netizen" will appear in the text.
- If there's no specific type match, they should be grouped into `Person`.
- Similarly, small organizations, temporary groups, etc., should be grouped into `Organization`.

**Principles for designing specific types**:
- Identify high-frequency or key character types from the text.
- Each specific type should have clear boundaries to avoid overlap.
- Description must clearly state the difference between this type and fallback types.

### 2. Relationship Type Design

- Quantity: 6-10 types.
- Relationships should reflect real connections in social media interactions.
- Ensure relationship source_targets cover your defined entity types.

### 3. Attribute Design

- 1-3 key attributes for each entity type.
- **Note**: Attribute names cannot use `name`, `uuid`, `group_id`, `created_at`, `summary` (these are system reserved words).
- Recommended use: `full_name`, `title`, `role`, `position`, `location`, `description`, etc.

## Entity Type Reference

**Individual (Specific)**:
- Student
- Professor
- Journalist
- Celebrity
- Executive
- Official
- Lawyer
- Doctor

**Individual (Fallback)**:
- Person: Any individual person (used when not belonging to specific types above)

**Organization (Specific)**:
- University
- Company
- GovernmentAgency
- MediaOutlet
- Hospital
- School
- NGO

**Organization (Fallback)**:
- Organization: Any organization (used when not belonging to specific types above)

## Relationship Type Reference

- WORKS_FOR
- STUDIES_AT
- AFFILIATED_WITH
- REPRESENTS
- REGULATES
- REPORTS_ON
- COMMENTS_ON
- RESPONDS_TO
- SUPPORTS
- OPPOSES
- COLLABORATES_WITH
- COMPETES_WITH
"""


class OntologyGenerator:
    """
    Ontology Generator
    Analyzes text content and generates entity and relationship type definitions.
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates ontology definition
        
        Args:
            document_texts: List of document texts
            simulation_requirement: Description of simulation requirements
            additional_context: Extra context
            
        Returns:
            Ontology definition (entity_types, edge_types, etc.)
        """
        # Build user message
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # Call LLM
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )
        
        # Validation and post-processing
        result = self._validate_and_process(result)
        
        return result
    
    # Maximum text length passed to LLM (50,000 characters)
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Builds user message"""
        
        # Merge texts
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)
        
        # Truncate if text exceeds 50,000 chars (only affects what is passed to LLM, not graph construction)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(Original text {original_length} chars, truncated to first {self.MAX_TEXT_LENGTH_FOR_LLM} chars for ontology analysis)..."
        
        message = f"""## Simulation Requirements

{simulation_requirement}

## Document Content

{combined_text}
"""
        
        if additional_context:
            message += f"""
## Additional Explanation

{additional_context}
"""
        
        message += """
Please design entity types and relationship types suitable for social media simulation based on the content above.

**Rules that MUST be followed**:
1. Must output EXACTLY 10 entity types.
2. The last 2 must be fallback types: Person and Organization.
3. The first 8 are specific types designed based on the text content.
4. All entity types must be subjects that can voice opinions in reality, not abstract concepts.
5. Attribute names cannot use reserved words like name, uuid, group_id; use full_name, org_name, etc., instead.
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validates and post-processes the result"""
        
        # Ensure required fields exist
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # Validate entity types
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # Ensure description doesn't exceed 100 characters
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."
        
        # Validate relationship types
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Zep API limits: max 10 custom entity types, max 10 custom edge types
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10
        
        # Fallback type definitions
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # Check if fallback types already exist
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # Fallbacks to add
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # If addition exceeds 10, remove some existing types
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # Calculate how many to remove
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # Remove from end (preserving more important specific types at the beginning)
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # Add fallback types
            result["entity_types"].extend(fallbacks_to_add)
        
        # Final check to ensure count doesn't exceed limits (defensive programming)
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        Converts ontology definition to Python code (similar to ontology.py).
        
        Args:
            ontology: Ontology definition
            
        Returns:
            Python code string
        """
        code_lines = [
            '"""',
            'Custom Entity Type Definitions',
            'Automatically generated by MiroFish for social media simulation.',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== Entity Type Definitions ==============',
            '',
        ]
        
        # Generate entity types
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append('        default=None')
                    code_lines.append('    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== Relationship Type Definitions ==============')
        code_lines.append('')
        
        # Generate relationship types
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # Convert to PascalCase class name
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append('        default=None')
                    code_lines.append('    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # Generate type dictionaries
        code_lines.append('# ============== Type Configuration ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # Generate edge source_targets mapping
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)
