// Top bar: app name, who is logged in, and logout.
export default function Header({ user, onLogout }) {
  return (
    <header className="header">
      <strong>Pramaan</strong>
      {user && (
        <span>
          {user.username} ({user.role}) <button onClick={onLogout}>Log out</button>
        </span>
      )}
    </header>
  );
}
