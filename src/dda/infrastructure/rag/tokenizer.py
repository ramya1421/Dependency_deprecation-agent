from functools import lru_cache

from transformers import AutoTokenizer, PreTrainedTokenizerBase

# The same model named in CLAUDE.md's stack for embeddings — using its real
# tokenizer (not an approximation like word count or a different model's
# vocab, e.g. tiktoken) is what makes the 512-token chunk cap meaningful.
_MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _tokenizer() -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(_MODEL_NAME)


def count_tokens(text: str) -> int:
    return len(_tokenizer().encode(text, add_special_tokens=False))
