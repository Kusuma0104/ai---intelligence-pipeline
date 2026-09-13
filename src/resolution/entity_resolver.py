import csv
import re
from pathlib import Path



# 50 known AI startups used as the deterministic seed list.
SEED_STARTUPS = [
    "OpenAI",
    "Anthropic",
    "Cohere",
    "Mistral AI",
    "xAI",
    "Hugging Face",
    "Scale AI",
    "Databricks",
    "Stability AI",
    "Perplexity",
    "Character AI",
    "Runway",
    "Midjourney",
    "Adept AI",
    "Inflection AI",
    "ElevenLabs",
    "Together AI",
    "Replicate",
    "LangChain",
    "Glean",
    "Harvey",
    "Cursor",
    "Writer",
    "Jasper",
    "Copy.ai",
    "Weights & Biases",
    "Figure AI",
    "Physical Intelligence",
    "Shield AI",
    "Anduril",
    "Sakana AI",
    "Thinking Machines Lab",
    "Safe Superintelligence",
    "Poolside",
    "Magic",
    "Imbue",
    "Character Technologies",
    "Abridge",
    "Hippocratic AI",
    "Sierra",
    "Decagon",
    "Adept",
    "Nscale",
    "Together Computer",
    "Vercel",
    "Groq",
    "DeepL",
    "Synthesia",
    "Truera",
    "Suno",
]


def normalize_name(name: str) -> str:
    """
    Convert company names into a deterministic canonical comparison form.

    Example:
        OpenAI
        Open AI
        OpenAI Inc.
        OpenAI, Inc.
    all become:
        openai
    """
    if not name:
        return ""

    value = name.lower().strip()

    # Remove common company suffixes.
    value = re.sub(
        r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|co)\b",
        "",
        value,
    )

    # Keep only letters and numbers.
    value = re.sub(r"[^a-z0-9]", "", value)

    return value


def build_aliases():
    """
    Explicit aliases for common company and product variations.
    Product aliases are grounded in well-known public product-to-company mappings.
    """
    pairs = {
        "Open AI": "OpenAI",
        "OpenAI Inc.": "OpenAI",
        "OpenAI, Inc.": "OpenAI",
        "ChatGPT": "OpenAI",
        "Sora": "OpenAI",
        "Anthropic AI": "Anthropic",
        "Claude": "Anthropic",
        "Mistral": "Mistral AI",
        "MistralAI": "Mistral AI",
        "Le Chat": "Mistral AI",
        "HuggingFace": "Hugging Face",
        "ScaleAI": "Scale AI",
        "StabilityAI": "Stability AI",
        "Stable Diffusion": "Stability AI",
        "Character.AI": "Character AI",
        "Eleven Labs": "ElevenLabs",
        "Weights and Biases": "Weights & Biases",
        "W&B": "Weights & Biases",
        "Copy AI": "Copy.ai",
        "Figure": "Figure AI",
        "Physical Intelligence AI": "Physical Intelligence",
        "Safe Superintelligence Inc": "Safe Superintelligence",
        "SSI": "Safe Superintelligence",
        "Grok": "xAI",
        "Cursor AI": "Cursor",
        "Perplexity AI": "Perplexity",
        "LangChain": "LangChain",
        "Together Computer": "Together AI",
    }
    return {normalize_name(raw): canonical for raw, canonical in pairs.items()}


class EntityResolver:
    def __init__(self, seed_names=None):
        self.seed_names = seed_names or SEED_STARTUPS
        self.aliases = build_aliases()

        self.normalized_seeds = {
            normalize_name(name): name
            for name in self.seed_names
        }

    def resolve(self, input_name: str):
        """
        Resolve an input name against the 50 known startup seeds.

        Matching order:
        1. Exact normalized match
        2. Explicit alias
        3. Fuzzy deterministic match
        4. No match
        """
        normalized = normalize_name(input_name)

        if not normalized:
            return {
                "input_name": input_name,
                "canonical_name": None,
                "match_type": "NO_MATCH",
                "score": 0.0,
            }

        # 1. Exact normalized match.
        if normalized in self.normalized_seeds:
            canonical = self.normalized_seeds[normalized]

            return {
                "input_name": input_name,
                "canonical_name": canonical,
                "match_type": "EXACT",
                "score": 100.0,
            }

        # 2. Explicit alias.
        if normalized in self.aliases:
            canonical = self.aliases[normalized]

            return {
                "input_name": input_name,
                "canonical_name": canonical,
                "match_type": "ALIAS",
                "score": 100.0,
            }




            seed_normalized = normalize_name(seed_name)

            score = fuzz.ratio(
                normalized,
                seed_normalized,
            )

            if score > best_score:
                best_score = score
                best_name = seed_nam


        return {
        "input_name": input_name,
        "canonical_name": None,
        "match_type": "NO_MATCH",
        "score": 0.0,
        }

    def resolve_many(self, names):
        return [self.resolve(name) for name in names]

    def canonical_or_self(self, name: str) -> str:
        result = self.resolve(name)
        return result["canonical_name"] or (name or "").strip()

    def save_mapping_log(self, results, output_path="data/entity_mapping_log.csv"):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "input_name",
                    "canonical_name",
                    "match_type",
                    "score",
                ],
            )

            writer.writeheader()
            writer.writerows(results)


def resolve_dataset(names, resolver=None):
    resolver = resolver or EntityResolver()
    seen = []
    unique = []
    for name in names:
        value = str(name or "").strip()
        if value and value not in seen:
            seen.append(value)
            unique.append(value)
    return resolver.resolve_many(unique)


def main():
    from src.config import DATA_DIR
    import pandas as pd

    resolver = EntityResolver()
    names = []

    startups = DATA_DIR / "startups_1000.csv"
    products = DATA_DIR / "products_1000.csv"
    jobs = DATA_DIR / "jobs_24h.csv"

    if startups.exists():
        df = pd.read_csv(startups)
        col = "content.entityName" if "content.entityName" in df.columns else "name"
        names.extend(df[col].dropna().astype(str).tolist())

    if products.exists():
        df = pd.read_csv(products)
        for col in ("content.startupName", "name"):
            if col in df.columns:
                names.extend(df[col].dropna().astype(str).tolist())
                break

    if jobs.exists():
        df = pd.read_csv(jobs)
        col = "content.company" if "content.company" in df.columns else "company"
        if col in df.columns:
            names.extend(df[col].dropna().astype(str).tolist())

    if not names:
        names = [
            "OpenAI",
            "Open AI",
            "OpenAI Inc.",
            "Anthropic",
            "MistralAI",
            "HuggingFace",
            "Scale AI",
            "Completely Unknown Company",
        ]

    results = resolve_dataset(names, resolver)
    resolver.save_mapping_log(results, DATA_DIR / "entity_mapping_log.csv")
    print(f"Mapped {len(results)} unique names -> data/entity_mapping_log.csv")


if __name__ == "__main__":
    main()
