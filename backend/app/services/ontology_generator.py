"""
Ontology Generation Service
Interface 1: Analyzes text content to generate entity and relationship type definitions suitable for social simulation.
"""

from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient



ONTOLOGY_SYSTEM_PROMPT = """You are an expert in knowledge graph ontology design. Your task is to analyze the given text content and simulation requirements, and design entity types and relationship types suitable for **social media public opinion simulation**.

**Important: You must output valid JSON format data and nothing else.**

## Core Task Background

We are building a **social media public opinion simulation system**. In this system:
- Each entity is an "account" or "subject" that can speak, interact, and disseminate information on social media.
- Entities will influence, forward, comment on, and respond to each other.
- We need to simulate the reactions of all parties and the information dissemination paths in a public opinion event.

Therefore, **entities must be real-world subjects that can speak and interact on social media**:

**Can be**:
- Specific individuals (public figures, parties involved, opinion leaders, experts, ordinary people)
- Companies, enterprises (including their official accounts)
- Organizations (universities, associations, NGOs, unions, etc.)
- Government departments, regulatory agencies
- Media organizations (newspapers, TV stations, self-media, websites)
- Social media platforms themselves
- Representatives of specific groups (such as alumni associations, fan groups, rights protection groups, etc.)

**Cannot be**:
- Abstract concepts (e.g., "public opinion", "emotion", "trend")
- Themes/topics (e.g., "academic integrity", "education reform")
- Viewpoints/attitudes (e.g., "supporters", "opponents")

## Output Format

Please output in JSON format, containing the following structure:

```json
{
    "entity_types": [
        {
            "name": "Entity type name (English, PascalCase)",
            "description": "Short description (English, no more than 100 characters)",
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
            "description": "Short description (English, no more than 100 characters)",
            "source_targets": [
                {"source": "Source entity type", "target": "Target entity type"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "A brief analysis of the text content (Chinese)"
}
```

## Design Guidelines (Extremely Important!)

### 1. Entity Type Design - Must be strictly followed

**Quantity requirement: Must be exactly 10 entity types**

**Hierarchy requirement (must include both specific types and fallback types)**:

Your 10 entity types must include the following hierarchy:

A. **Fallback types (must be included, placed at the end of the list)**:
   - `Person`: A fallback type for any natural person. When a person does not belong to other more specific person types, they are classified into this category.
   - `Organization`: A fallback type for any organization. When an organization does not belong to other more specific organization types, it is classified into this category.

B. **Specific types (8 types, designed based on the text content)**:
   - Design more specific types for the main roles that appear in the text.
   - For example: if the text involves an academic event, there can be `Student`, `Professor`, `University`.
   - For example: if the text involves a commercial event, there can be `Company`, `CEO`, `Employee`.

**Why are fallback types needed**:
- Various characters will appear in the text, such as "primary and secondary school teachers", "passerby A", "a certain netizen".
- If there is no specific type to match, they should be classified as `Person`.
- Similarly, small organizations, temporary groups, etc. should be classified as `Organization`.

**Principles for designing specific types**:
- Identify high-frequency or key role types from the text.
- Each specific type should have clear boundaries to avoid overlap.
- The description must clearly explain the difference between this type and the fallback type.

### 2. Relationship Type Design

- Quantity: 6-10
- Relationships should reflect real connections in social media interactions.
- Ensure that the source_targets of the relationships cover the entity types you define.

### 3. Attribute Design

- 1-3 key attributes for each entity type.
- **Note**: Attribute names cannot be `name`, `uuid`, `group_id`, `created_at`, `summary` (these are system reserved words).
- Recommended to use: `full_name`, `title`, `role`, `position`, `location`, `description`, etc.

## Entity Type Reference

**Individual (Specific)**:
- Student
- Professor/Scholar
- Journalist
- Celebrity/Influencer
- Executive
- Official
- Lawyer
- Doctor

**Individual (Fallback)**:
- Person: Any natural person (used when not belonging to the above specific types)

**Organization (Specific)**:
- University
- Company
- GovernmentAgency
- MediaOutlet
- Hospital
- School
- NGO

**Organization (Fallback)**:
- Organization: Any organization (used when not belonging to the above specific types)

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
    Analyzes text content to generate entity and relationship type definitions.
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
        Generates an ontology definition.
        
        Args:
            document_texts: List of document texts.
            simulation_requirement: Description of the simulation requirement.
            additional_context: Additional context.
            
        Returns:
            Ontology definition (entity_types, edge_types, etc.).
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
        
        # Validate and post-process
        result = self._validate_and_process(result)
        
        return result
    
    # Maximum text length to pass to the LLM (50,000 characters)
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Builds the user message."""
        
        # Combine texts
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)
        
        # Truncate if the text exceeds 50,000 characters (only affects the content passed to the LLM, not the graph construction)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(Original text has {original_length} characters, the first {self.MAX_TEXT_LENGTH_FOR_LLM} characters have been extracted for ontology analysis)..."
        
        message = f"""## Simulation Requirement

{simulation_requirement}

## Document Content

{combined_text}
"""
        
        if additional_context:
            message += f"""
## Additional Information

{additional_context}
"""
        
        message += """
Please design entity types and relationship types suitable for social media public opinion simulation based on the above content.

**Rules to follow**:
1. You must output exactly 10 entity types.
2. The last 2 must be fallback types: Person (for individuals) and Organization (for organizations).
3. The first 8 are specific types designed based on the text content.
4. All entity types must be real-world subjects that can express opinions, not abstract concepts.
5. Attribute names cannot be reserved words like name, uuid, group_id, etc. Use alternatives like full_name, org_name, etc.
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validates and post-processes the result."""
        
        # Ensure necessary fields exist
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
            # Ensure description does not exceed 100 characters
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
        
        # Graphiti API limits: max 10 custom entity types, max 10 custom edge types
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
        
        # Fallback types to add
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # If adding will exceed 10, remove some existing types
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # Calculate how many to remove
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # Remove from the end (to keep the more important specific types at the front)
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # Add fallback types
            result["entity_types"].extend(fallbacks_to_add)
        
        # Finally, ensure limits are not exceeded (defensive programming)
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        Converts ontology definition to Python code (similar to ontology.py).
        
        Args:
            ontology: Ontology definition.
            
        Returns:
            Python code string.
        """
        code_lines = [
            '"""',
            'Custom entity type definitions',
            'Automatically generated by MiroFish for social public opinion simulation',
            '"""',
            '',
            'from pydantic import Field',
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
        code_lines.append('# ============== Type Configurations ==============')
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

