// Reads a QR code with the webcam (or from a saved picture of one) and calls onResult(text).
//
// How it works: the camera stream plays in a <video>; a few times a second we copy the
// current frame onto a hidden <canvas> and give its pixels to jsQR, which finds and decodes
// a QR code if there is one. Browsers only allow the camera on https or on localhost.
import jsQR from "jsqr";
import { useEffect, useRef, useState } from "react";

function decode(canvas, source, width, height) {
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(source, 0, 0, width, height);
  const found = jsQR(ctx.getImageData(0, 0, width, height).data, width, height);
  return found?.data || null;
}

export default function QrScanner({ onResult }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!scanning) return;
    if (!navigator.mediaDevices) {
      setError("This browser can't use the camera here (it needs https or localhost). Type the code instead.");
      setScanning(false);
      return;
    }
    let stream = null;
    let timer = null;
    let stopped = false;

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        if (stopped) return s.getTracks().forEach((t) => t.stop());
        stream = s;
        videoRef.current.srcObject = s;
        videoRef.current.play();
        timer = setInterval(() => {
          const v = videoRef.current;
          if (!v || v.readyState < 2) return; // camera not ready yet
          const text = decode(canvasRef.current, v, v.videoWidth, v.videoHeight);
          if (text) {
            setScanning(false);
            onResult(text);
          }
        }, 250);
      })
      .catch(() => {
        setError("Could not open the camera. Allow camera access, or type the code instead.");
        setScanning(false);
      });

    // turn the camera off when scanning stops or the page closes
    return () => {
      stopped = true;
      clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [scanning, onResult]);

  function readPicture(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const img = new Image();
    img.onload = () => {
      const text = decode(canvasRef.current, img, img.naturalWidth, img.naturalHeight);
      URL.revokeObjectURL(img.src);
      if (text) onResult(text);
      else setError("No QR code found in that picture.");
    };
    img.src = URL.createObjectURL(file);
  }

  return (
    <div className="qr-scanner">
      {scanning ? (
        <>
          <video ref={videoRef} muted playsInline aria-label="Camera view: hold the QR code in front of the camera" />
          <button className="btn-secondary" onClick={() => setScanning(false)}>Stop camera</button>
        </>
      ) : (
        <span className="card-actions">
          <button className="btn-primary" onClick={() => { setError(""); setScanning(true); }}>
            Scan QR with camera
          </button>
          <label className="btn-secondary file-button">
            Use a picture of the QR
            <input type="file" accept="image/*" onChange={readPicture} hidden />
          </label>
        </span>
      )}
      <canvas ref={canvasRef} hidden />
      {error && <p className="error">{error}</p>}
    </div>
  );
}
