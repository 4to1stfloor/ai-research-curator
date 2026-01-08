"""Summary image generation using Google Gemini."""

import base64
from pathlib import Path
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Paper


class SummaryImageGenerator:
    """Generate summary images for papers using Google Gemini."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash-exp",
        output_dir: str | Path = "./output/images"
    ):
        """
        Initialize image generator.

        Args:
            api_key: Google API key
            model: Gemini model to use
            output_dir: Directory to save generated images
        """
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    def generate_summary_image(
        self,
        paper: Paper,
        summary: str,
        style: str = "scientific"
    ) -> Optional[str]:
        """
        Generate a summary image for a paper.

        Args:
            paper: Paper object
            summary: Paper summary text
            style: Image style ("scientific", "infographic", "flowchart")

        Returns:
            Path to generated image, or None if failed
        """
        # Create prompt for image generation
        prompt = self._create_image_prompt(paper, summary, style)

        try:
            # Generate image using Gemini
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "image/png"
                }
            )

            # Check if image was generated
            if response.parts:
                for part in response.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        # Save image
                        image_data = base64.b64decode(part.inline_data.data)
                        filename = self._create_filename(paper)
                        output_path = self.output_dir / filename

                        with open(output_path, 'wb') as f:
                            f.write(image_data)

                        print(f"Generated image: {output_path}")
                        return str(output_path)

            print("No image generated in response")
            return None

        except Exception as e:
            print(f"Error generating image: {e}")
            return None

    def _create_image_prompt(
        self,
        paper: Paper,
        summary: str,
        style: str
    ) -> str:
        """Create prompt for image generation."""
        style_instructions = {
            "scientific": "Create a scientific diagram style illustration",
            "infographic": "Create an infographic style visualization",
            "flowchart": "Create a flowchart showing the research process"
        }

        prompt = f"""
{style_instructions.get(style, style_instructions['scientific'])} for this research paper:

Title: {paper.title}

Summary: {summary[:500]}

The image should:
1. Be clear and professional
2. Use appropriate colors for scientific visualization
3. Include key concepts and their relationships
4. Be suitable for a research summary
5. Not include any text that might be hard to read

Create a visually appealing summary diagram.
"""
        return prompt

    def _create_filename(self, paper: Paper) -> str:
        """Create safe filename for image."""
        import re
        safe_title = re.sub(r'[<>:"/\\|?*]', '', paper.title)
        safe_title = re.sub(r'\s+', '_', safe_title)[:50]
        return f"{safe_title}_summary.png"


class MermaidRenderer:
    """Render Mermaid diagrams to images."""

    def __init__(self, output_dir: str | Path = "./output/diagrams"):
        """
        Initialize Mermaid renderer.

        Args:
            output_dir: Directory to save rendered diagrams
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_to_svg(
        self,
        mermaid_code: str,
        filename: str
    ) -> Optional[str]:
        """
        Render Mermaid code to SVG.

        Note: Requires mermaid-cli (mmdc) to be installed.
        Install with: npm install -g @mermaid-js/mermaid-cli

        Args:
            mermaid_code: Mermaid diagram code
            filename: Output filename (without extension)

        Returns:
            Path to SVG file, or None if failed
        """
        import subprocess
        import tempfile

        output_path = self.output_dir / f"{filename}.svg"

        try:
            # Write mermaid code to temp file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.mmd',
                delete=False
            ) as f:
                f.write(mermaid_code)
                temp_input = f.name

            # Run mmdc
            result = subprocess.run(
                ['mmdc', '-i', temp_input, '-o', str(output_path)],
                capture_output=True,
                text=True,
                timeout=30
            )

            # Clean up
            Path(temp_input).unlink()

            if result.returncode == 0:
                print(f"Rendered diagram: {output_path}")
                return str(output_path)
            else:
                print(f"Mermaid render error: {result.stderr}")
                return None

        except FileNotFoundError:
            print("mermaid-cli (mmdc) not found. Install with: npm install -g @mermaid-js/mermaid-cli")
            return None
        except Exception as e:
            print(f"Error rendering Mermaid: {e}")
            return None

    def save_as_markdown(
        self,
        mermaid_code: str,
        filename: str,
        title: Optional[str] = None
    ) -> str:
        """
        Save Mermaid code as markdown file (for Obsidian).

        Args:
            mermaid_code: Mermaid diagram code
            filename: Output filename (without extension)
            title: Optional title for the diagram

        Returns:
            Path to markdown file
        """
        output_path = self.output_dir / f"{filename}.md"

        content = []
        if title:
            content.append(f"# {title}\n")

        content.append("```mermaid")
        content.append(mermaid_code)
        content.append("```")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))

        return str(output_path)


class DiagramGenerator:
    """Generate diagrams for papers (combining LLM + rendering)."""

    def __init__(
        self,
        llm_client,
        output_dir: str | Path = "./output/diagrams"
    ):
        """
        Initialize diagram generator.

        Args:
            llm_client: LLM client for generating diagram descriptions
            output_dir: Directory to save diagrams
        """
        from .summarizer import ImageDescriptionGenerator

        self.desc_generator = ImageDescriptionGenerator(llm_client)
        self.renderer = MermaidRenderer(output_dir)

    def generate_diagram(
        self,
        paper: Paper,
        summary: str,
        render_svg: bool = False
    ) -> dict:
        """
        Generate diagram for paper.

        Args:
            paper: Paper object
            summary: Paper summary
            render_svg: Whether to render to SVG (requires mmdc)

        Returns:
            Dict with mermaid_code, markdown_path, and optionally svg_path
        """
        # Generate Mermaid code
        mermaid_code = self.desc_generator.generate_mermaid(paper, summary)

        # Create safe filename
        import re
        safe_title = re.sub(r'[<>:"/\\|?*]', '', paper.title)
        safe_title = re.sub(r'\s+', '_', safe_title)[:50]

        result = {
            "mermaid_code": mermaid_code,
            "markdown_path": self.renderer.save_as_markdown(
                mermaid_code,
                safe_title,
                title=f"Diagram: {paper.title}"
            )
        }

        # Optionally render to SVG
        if render_svg:
            svg_path = self.renderer.render_to_svg(mermaid_code, safe_title)
            if svg_path:
                result["svg_path"] = svg_path

        return result
