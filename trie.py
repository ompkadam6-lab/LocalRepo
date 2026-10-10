class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end = False
        self.values = []


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word, value=None):
        if not word:
            return
        node = self.root
        for char in word.lower().strip():
            node = node.children.setdefault(char, TrieNode())
        node.is_end = True
        stored = value if value is not None else word
        if stored not in node.values:
            node.values.append(stored)

    def starts_with(self, prefix):
        if prefix is None:
            return []
        prefix = prefix.lower().strip()
        node = self.root
        for char in prefix:
            if char not in node.children:
                return []
            node = node.children[char]

        results = []
        self._collect(node, results)
        return results

    def _collect(self, node, results):
        for value in node.values:
            if value not in results:
                results.append(value)
        for child in node.children.values():
            self._collect(child, results)
