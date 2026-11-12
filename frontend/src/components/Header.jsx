// Top bar: app name, who is logged in, and logout.
export default function Header({ user, onLogout }) {
  return (
    <header className="header">
      <strong>Pramaan</strong>
      {user && (
        <span className="header-user">
          {user.username} ({user.role}) <button className="btn-secondary" onClick={onLogout}>Log out</button>
        </span>
      )}
    </header>
  );
}
