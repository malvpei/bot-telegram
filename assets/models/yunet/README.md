# YuNet face detector

`face_detection_yunet_2023mar.onnx` is the unmodified YuNet model distributed by
[OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet).
Its MIT license and copyright notice are included in `LICENSE`.

- Source revision: `47534e27c9851bb1128ccc0102f1145e27f23f98`.
- Model size: 232,589 bytes.
- SHA-256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`.
- The download is verified against the SHA-256 in OpenCV Zoo's Git LFS pointer.
- This 2023 model works with the project's OpenCV 4.x dependency. The newer
  2026 export targets OpenCV 5's ONNX Runtime backend and is not required here.

The application loads this local asset without network access. YuNet complements
the existing frontal/profile cascades; it does not identify people. Missing
models, unavailable OpenCV features, and inference errors fall back to cascades.

The wrapper follows OpenCV's
[FaceDetectorYN API](https://docs.opencv.org/4.x/df/d20/classcv_1_1FaceDetectorYN.html):
input is converted from RGB to BGR and detected boxes are restored to the
caller's image coordinates. Images are downscaled to at most 640 pixels along
the long edge. If no face is found, a 320-pixel view also checks close portraits,
because the model is trained for faces approximately 10–300 pixels across.
Very small, heavily occluded, or unusual poses can still be missed.
