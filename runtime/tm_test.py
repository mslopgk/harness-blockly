import os, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tm

rng = np.random.default_rng(0)
def frames(channel, n):
    a = np.zeros((n, 224, 224, 3), np.uint8); a[..., channel] = 200
    return np.clip(a + rng.integers(-30, 30, (n, 224, 224, 3)), 0, 255).astype(np.uint8)

class TMTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.red = frames(2, 6)   # BGR ch2 = red after BGR->RGB flip
        cls.blue = frames(0, 6)
        cls.model = tm.Model(["red", "blue"])
        for f in cls.red: cls.model.add_example(f, "red")
        for f in cls.blue: cls.model.add_example(f, "blue")
        cls.model.train(epochs=30)

    def test_predict_holdout(self):
        for f in frames(2, 3): self.assertEqual(self.model.predict(f)[0], "red")
        for f in frames(0, 3): self.assertEqual(self.model.predict(f)[0], "blue")

    def test_predict_proba_and_labels(self):
        p = self.model.predict_proba(self.red[0])
        self.assertEqual(set(p.keys()), {"red", "blue"})
        self.assertAlmostEqual(sum(p.values()), 1.0, places=3)
        self.assertEqual(self.model.labels, ["red", "blue"])

    def test_save_load_roundtrip(self):
        d = tempfile.mkdtemp(); path = os.path.join(d, "m.npz")
        self.model.save(path)
        m2 = tm.load_model(path)
        self.assertEqual(m2.labels, ["red", "blue"])
        self.assertEqual(m2.predict(frames(2, 1)[0])[0], "red")

    def test_errors(self):
        with self.assertRaises(ValueError): tm.Model(["only"])            # <2 classes
        m = tm.Model(["a", "b"])
        with self.assertRaises(ValueError): m.add_example(self.red[0], "z")  # unknown label
        with self.assertRaises(RuntimeError): m.predict(self.red[0])         # not trained
        m.add_example(self.red[0], "a")
        with self.assertRaises(RuntimeError): m.train()                      # class 'b' empty

if __name__ == "__main__":
    unittest.main(verbosity=2)
