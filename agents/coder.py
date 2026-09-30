from pydantic import BaseModel, Field, ValidationError

from agents.base import Agent
from core.util import parse_json_llm


class ProposedFile(BaseModel):
    path: str = Field(min_length=1)
    content: str


class CodeProposal(BaseModel):
    summary: str
    files: list[ProposedFile]


class Coder(Agent):

    name = "coder"

    def run(self, goal: str, objective: str, context: str = "") -> CodeProposal:
        system = """
Você é o CODER.

Você NÃO executa código.

Você produz uma PROPOSTA de arquivos.

Regras:

1. Não use shell.
2. Não inclua credenciais.
3. Não tente acessar sistemas externos.
4. Não use caminhos absolutos.
5. Todos os caminhos devem ser relativos ao workspace.
6. Não use "..".
7. Não escreva arquivos fora do workspace.
8. Responda somente JSON.

Formato:

{
  "summary": "descrição",
  "files": [
    {
      "path": "src/example.py",
      "content": "..."
    }
  ]
}
"""

        prompt = f"""
<goal>
{goal}
</goal>

<objective>
{objective}
</objective>

<context>
{context}
</context>

Crie somente os arquivos necessários.
Não execute nada.
"""

        raw = self.router.ask("coder", system, prompt)
        try:
            data = parse_json_llm(raw)
            return CodeProposal.model_validate(data)
        except (ValueError, ValidationError):
            # Resposta malformada (glitch intermitente do backend) — uma
            # repetição in-place é mais barata que um replan completo.
            raw = self.router.ask("coder", system, prompt)
            try:
                data = parse_json_llm(raw)
                return CodeProposal.model_validate(data)
            except (ValueError, ValidationError) as exc:
                raise ValueError(
                    f"Coder não produziu proposta JSON válida após 2 tentativas "
                    f"({exc}). Resposta crua[:400]: {raw[:400]!r}"
                ) from None
