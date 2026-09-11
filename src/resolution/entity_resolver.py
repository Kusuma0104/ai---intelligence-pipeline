import csv
import re
from pathlib import Path

from rapidfuzz import fuzz


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
    Explicit aliases for common variations.
    """
    return {
        normalize_name("Open AI"): "OpenAI",
        normalize_name("OpenAI Inc."): "OpenAI",
        normalize_name("OpenAI, Inc."): "OpenAI",
        normalize_name("Anthropic AI"): "Anthropic",
        normalize_name("Mistral"): "Mistral AI",
        normalize_name("MistralAI"): "Mistral AI",
        normalize_name("HuggingFace"): "Hugging Face",
        normalize_name("ScaleAI"): "Scale AI",
        normalize_name("StabilityAI"): "Stability AI",
        normalize_name("Character.AI"): "Character AI",
        normalize_name("Eleven Labs"): "ElevenLabs",
        normalize_name("Weights and Biases"): "Weights & Biases",
        normalize_name("Copy AI"): "Copy.ai",
        normalize_name("Figure"): "Figure AI",
        normalize_name("Physical Intelligence AI"): "Physical Intelligence",
        normalize_name("Safe Superintelligence Inc"): "Safe Superintelligence",
    }


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

        # 3. Deterministic fuzzy matching.
        best_name = None
        best_score = 0.0

        for seed_name in self.seed_names:
            seed_normalized = normalize_name(seed_name)

            score = fuzz.ratio(
                normalized,
                seed_normalized,
            )

            if score > best_score:
                best_score = score
                best_name = seed_name

        # High threshold to avoid unsafe false matches.
        if best_score >= 90:
            return {
                "input_name": input_name,
                "canonical_name": best_name,
                "match_type": "FUZZY",
                "score": round(best_score, 2),
            }

        return {
            "input_name": input_name,
            "canonical_name": None,
            "match_type": "NO_MATCH",
            "score": round(best_score, 2),
        }

    def resolve_many(self, names):
        return [self.resolve(name) for name in names]

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


def main():
    resolver = EntityResolver()

    test_names = [
        "OpenAI",
        "Open AI",
        "OpenAI Inc.",
        "Anthropic",
        "MistralAI",
        "HuggingFace",
        "Scale AI",
        "Completely Unknown Company",
    ]

    results = resolver.resolve_many(test_names)

    print("\nEntity Resolution Results:\n")

    for result in results:
        print(result)

    resolver.save_mapping_log(results)

    print("\nMapping log saved to:")
    print("data/entity_mapping_log.csv")


if __name__ == "__main__":
    main()