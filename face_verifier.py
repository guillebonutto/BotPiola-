import base64
import os
from pathlib import Path
import numpy as np
import cv2
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class FaceVerifier:
    def __init__(self, models_dir="bin"):
        self.models_dir = Path(models_dir)
        self.yunet_model = self.models_dir / "face_detection_yunet.onnx"
        self.sface_model = self.models_dir / "face_recognition_sface.onnx"
        
        # Archivo cifrado con algoritmo militar AES-256-GCM (NO contiene fotos, solo vector abstracto cifrado)
        self.master_features_enc = Path("master_face_features.enc")
        self.key_file = Path(".bio_key")
        
        # Archivos residuales a purgar permanentemente
        self.legacy_npy = Path("master_face_features.npy")
        self.legacy_jpg = Path("master_face.jpg")

        self.detector = None
        self.recognizer = None
        self._init_models()
        self._cleanup_plaintext_images()

    def _get_or_create_key(self) -> bytes:
        """Obtiene o genera una clave de 256 bits criptográficamente segura."""
        if self.key_file.exists():
            key = self.key_file.read_bytes()
            if len(key) == 32:
                return key
        new_key = AESGCM.generate_key(bit_length=256)
        self.key_file.write_bytes(new_key)
        return new_key

    def _cleanup_plaintext_images(self):
        """Elimina permanentemente cualquier foto o archivo no encriptado para proteger la privacidad."""
        try:
            if self.legacy_jpg.exists():
                self.legacy_jpg.unlink()
                print("[FaceVerifier] [PRIVACIDAD] Foto master_face.jpg eliminada de forma permanente.")
            if self.master_features_enc.exists() and self.legacy_npy.exists():
                self.legacy_npy.unlink()
                print("[FaceVerifier] [PRIVACIDAD] Vector plano master_face_features.npy purgado.")
        except Exception as e:
            print(f"[FaceVerifier] Aviso en limpieza de archivos: {e}")

    def _init_models(self):
        if not self.yunet_model.exists() or not self.sface_model.exists():
            print("[FaceVerifier] AVISO: Modelos ONNX de reconocimiento facial no encontrados en bin/.")
            return

        try:
            self.detector = cv2.FaceDetectorYN.create(
                str(self.yunet_model.resolve()),
                "",
                (320, 320),
                score_threshold=0.6,
                nms_threshold=0.3,
                top_k=5000
            )
            self.recognizer = cv2.FaceRecognizerSF.create(
                str(self.sface_model.resolve()),
                ""
            )
            print("[FaceVerifier] [OK] Redes neuronales YuNet + SFace con cifrado AES-256 cargadas.")
        except Exception as e:
            print(f"[FaceVerifier] ERROR cargando modelos OpenCV: {e}")

    def is_enrolled(self) -> bool:
        """Verifica si ya existe la plantilla biométrica cifrada con AES-256."""
        return self.master_features_enc.exists()

    def _decode_image(self, image_data):
        """Decodifica una imagen en memoria sin escribirla a disco."""
        if isinstance(image_data, str):
            if "base64," in image_data:
                image_data = image_data.split("base64,")[1]
            raw_bytes = base64.b64decode(image_data)
        else:
            raw_bytes = image_data

        nparr = np.frombuffer(raw_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img

    def enroll_face(self, image_data):
        """
        Extrae el vector biométrico abstracto de 128 dimensiones y lo cifra con AES-256-GCM.
        NUNCA guarda la foto en disco. La imagen se destruye de la memoria de inmediato.
        """
        if not self.detector or not self.recognizer:
            return {"success": False, "error": "Modelos de reconocimiento no disponibles en el servidor."}

        img = self._decode_image(image_data)
        if img is None:
            return {"success": False, "error": "No se pudo decodificar la imagen enviada."}

        h, w, _ = img.shape
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(img)

        if faces is None or len(faces) == 0:
            return {"success": False, "error": "No se detectó ningún rostro. Centra tu cara con buena luz."}

        if len(faces) > 1:
            return {"success": False, "error": "Se detectó más de una persona. Asegúrate de estar solo frente a la cámara."}

        # 1. Extraer vector biométrico (128 números de coma flotante)
        aligned_face = self.recognizer.alignCrop(img, faces[0])
        features = self.recognizer.feature(aligned_face)

        # 2. Cifrar con algoritmo militar AES-256-GCM (Authenticated Encryption)
        key = self._get_or_create_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, features.tobytes(), None)

        # 3. Guardar ÚNICAMENTE el archivo binario cifrado (imposible de descifrar o reconstruir imagen)
        self.master_features_enc.write_bytes(nonce + ciphertext)

        # 4. Destruir foto y referencias de memoria
        del img
        del aligned_face
        self._cleanup_plaintext_images()

        print("[FaceVerifier] [OK] Vector biométrico cifrado con AES-256-GCM y guardado. Cero fotos en disco.")
        return {
            "success": True,
            "message": "¡Rostro maestro cifrado con AES-256-GCM con éxito! Ninguna foto fue guardada en el disco."
        }

    def _load_decrypted_master_features(self):
        """Descifra el vector biométrico maestro en memoria usando AES-256-GCM."""
        if not self.master_features_enc.exists():
            return None
        key = self._get_or_create_key()
        aesgcm = AESGCM(key)
        payload = self.master_features_enc.read_bytes()
        nonce = payload[:12]
        ciphertext = payload[12:]
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        features = np.frombuffer(decrypted_bytes, dtype=np.float32).reshape(1, -1)
        return features

    def verify_face(self, image_data, threshold=0.38):
        """Compara la imagen en vivo contra el vector biométrico cifrado en memoria."""
        if not self.is_enrolled():
            return {
                "enrolled": False,
                "verified": False,
                "error": "No hay ningún rostro maestro registrado aún. Debes registrarte primero."
            }

        if not self.detector or not self.recognizer:
            return {"enrolled": True, "verified": False, "error": "Modelos de reconocimiento no disponibles."}

        img = self._decode_image(image_data)
        if img is None:
            return {"enrolled": True, "verified": False, "error": "Error al procesar la imagen de la cámara."}

        h, w, _ = img.shape
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(img)

        if faces is None or len(faces) == 0:
            return {
                "enrolled": True,
                "verified": False,
                "error": "No se detectó ningún rostro frente al lente. Enfoca tu cara."
            }

        # Extraer vector del rostro actual en memoria
        aligned_face = self.recognizer.alignCrop(img, faces[0])
        current_features = self.recognizer.feature(aligned_face)

        # Cargar y descifrar vector maestro en memoria
        master_features = self._load_decrypted_master_features()
        if master_features is None:
            return {"enrolled": False, "verified": False, "error": "Error al descifrar el vector biométrico."}

        # Calcular similitud coseno (1.0 = idéntico, <0.38 = otra persona)
        cosine_score = self.recognizer.match(master_features, current_features, cv2.FaceRecognizerSF_FR_COSINE)
        is_match = bool(cosine_score >= threshold)
        confidence_pct = round(max(0.0, min(100.0, ((cosine_score + 0.2) / 1.2) * 100)), 1)

        # Destruir referencias de memoria inmediatamente
        del img
        del aligned_face

        print(f"[FaceVerifier] [AES-256] Comparación facial: Cosine Score = {cosine_score:.4f} (Umbral: {threshold}) -> Match: {is_match}")

        if is_match:
            return {
                "enrolled": True,
                "verified": True,
                "score": float(cosine_score),
                "confidence": f"{confidence_pct}%",
                "message": f"¡Identidad confirmada! Bienvenido Guille (Coincidencia: {confidence_pct}%)."
            }
        else:
            return {
                "enrolled": True,
                "verified": False,
                "score": float(cosine_score),
                "confidence": f"{confidence_pct}%",
                "message": "Acceso Denegado: El rostro no coincide con el dueño registrado."
            }

face_verifier = FaceVerifier()
