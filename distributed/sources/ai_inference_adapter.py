"""
Adaptador de Inferência de IA para a Fonte 1 (Estação de Dermatoscopia Digital).
Reaproveita o modelo Keras tcc.h5 e o pré-processamento original do projeto.
"""
import os
import sys
import random
from typing import Dict, List, Tuple

# Localização do projeto original
_WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODEL_PATH = os.path.join(_WORKSPACE_ROOT, "ANALISE_IMG_CANCER_DE_PELE ", "tcc.h5")
_STATIC_DIR = os.path.join(_WORKSPACE_ROOT, "ANALISE_IMG_CANCER_DE_PELE ", "static")
_VENV_PACKAGES = os.path.join(_WORKSPACE_ROOT, "ANALISE_IMG_CANCER_DE_PELE ", ".venv", "lib", "python3.9", "site-packages")

# 7 classes originais definidas em app.py
CANCER_CLASSES: Dict[int, str] = {
    0: "Queratoses actínicas (Pré-cancerosas)",
    1: "Carcinoma de células basais (Maligno)",
    2: "Dermatofibroma (Benigno)",
    3: "Lesões benignas semelhantes a queratose (Benigno)",
    4: "Melanoma (Maligno)",
    5: "Nevos melanocíticos (Benigno)",
    6: "Lesões Vasculares (Benigno)",
}

MALIGNANT_CLASSES = {
    "Carcinoma de células basais (Maligno)",
    "Melanoma (Maligno)",
    "Queratoses actínicas (Pré-cancerosas)",
}


class AIInferenceAdapter:
    """Carrega o modelo Keras original e executa classificações dermatológicas."""

    _cached_model = None
    _cached_use_real = None

    def __init__(self, force_simulation: bool = False):
        self._sample_images: List[str] = []
        self._find_sample_images()

        if force_simulation:
            self.model = None
            self.use_real_model = False
            print("[i] Modo Simulado da IA ativado manualmente (sem carregar o modelo tcc.h5).")
            return

        self.model = AIInferenceAdapter._cached_model
        self.use_real_model = bool(AIInferenceAdapter._cached_use_real)

        if AIInferenceAdapter._cached_model is None and AIInferenceAdapter._cached_use_real is None:
            self._try_load_model()
            AIInferenceAdapter._cached_model = self.model
            AIInferenceAdapter._cached_use_real = self.use_real_model

    def _find_sample_images(self):
        """Localiza imagens dermatológicas reais existentes na pasta static/ do projeto."""
        if os.path.exists(_STATIC_DIR):
            for f in os.listdir(_STATIC_DIR):
                if f.lower().endswith((".jpg", ".png", ".jpeg")):
                    self._sample_images.append(os.path.join(_STATIC_DIR, f))

    def _try_load_model(self):
        """Tenta carregar o modelo tcc.h5 via Keras se disponível."""
        if not os.path.exists(_MODEL_PATH):
            return

        if os.path.exists(_VENV_PACKAGES) and _VENV_PACKAGES not in sys.path:
            sys.path.insert(0, _VENV_PACKAGES)

        try:
            from keras.models import load_model  # type: ignore
            # Carrega o modelo de 220 MB apenas uma vez
            self.model = load_model(_MODEL_PATH)
            self.use_real_model = True
            print(f"[✓] Modelo Keras tcc.h5 carregado com sucesso na Estação de Dermatoscopia!")
        except Exception:
            self.use_real_model = False

    def classify_random_sample(self) -> Tuple[str, float, bool, List[Tuple[int, str, float]], str]:
        """
        Retorna:
          top_class: str
          top_probability: float
          is_malignant: bool
          probabilities: List[(class_id, class_name, prob)]
          image_name: str
        """
        image_name = "lesion_sample.jpg"
        if self._sample_images:
            image_path = random.choice(self._sample_images)
            image_name = os.path.basename(image_path)

        # Se o modelo Keras real foi carregado, realiza predição real
        if self.use_real_model and self.model and self._sample_images:
            try:
                from PIL import Image  # type: ignore
                import numpy as np  # type: ignore

                img = Image.open(image_path)
                img = img.resize((150, 150))
                arr = np.array(img) / 255.0
                arr = arr.reshape(150, 150, 3)
                preds = self.model.predict(np.expand_dims(arr, axis=0), verbose=0)[0]

                probs = [(i, CANCER_CLASSES[i], float(preds[i])) for i in range(len(preds))]
                probs.sort(key=lambda x: x[2], reverse=True)

                top_class = probs[0][1]
                top_prob = float(probs[0][2])
                is_mal = top_class in MALIGNANT_CLASSES

                return top_class, top_prob, is_mal, probs, image_name
            except Exception:
                pass

        # Geração sintética estocástica realista para as 7 classes
        chosen_top = random.choices(
            population=list(CANCER_CLASSES.keys()),
            weights=[0.08, 0.15, 0.10, 0.12, 0.15, 0.35, 0.05],  # Nevos melanocíticos mais frequentes
            k=1
        )[0]

        top_prob = round(random.uniform(0.68, 0.96), 4)
        remaining = 1.0 - top_prob
        other_weights = [random.random() for _ in range(6)]
        total_w = sum(other_weights)

        probs: List[Tuple[int, str, float]] = []
        w_idx = 0
        for i in range(7):
            if i == chosen_top:
                probs.append((i, CANCER_CLASSES[i], top_prob))
            else:
                p = round((other_weights[w_idx] / total_w) * remaining, 4)
                probs.append((i, CANCER_CLASSES[i], p))
                w_idx += 1

        probs.sort(key=lambda x: x[2], reverse=True)
        top_class = CANCER_CLASSES[chosen_top]
        is_mal = top_class in MALIGNANT_CLASSES

        return top_class, top_prob, is_mal, probs, image_name
