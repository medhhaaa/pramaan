import logoUrl from '../assets/pramaan-logo.png';

// Your hand-drawn logo (src/assets/pramaan-logo.png). It sits on a white plate so the
// blue ink reads on both the dark and light themes.
export default function Logo({ compact = false }) {
  return (
    <div className={`logo ${compact ? 'logo-compact' : ''}`}>
      <span className="logo-plate">
        <img src={logoUrl} alt="Pramaan" className="logo-img" />
      </span>
    </div>
  );
}
