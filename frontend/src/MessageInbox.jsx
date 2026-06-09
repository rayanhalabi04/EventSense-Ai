import { useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export default function MessageInbox() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");

    if (!token) {
      setError("Sign in to view the inbox.");
      setIsLoading(false);
      return;
    }

    fetch(`${API_BASE_URL}/api/v1/inbox/messages`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Unable to load inbox.");
        }
        return response.json();
      })
      .then(setRows)
      .catch((fetchError) => setError(fetchError.message))
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) {
    return <main style={styles.page}>Loading inbox...</main>;
  }

  if (error) {
    return <main style={styles.page}>{error}</main>;
  }

  return (
    <main style={styles.page}>
      <h1 style={styles.title}>Message Inbox</h1>
      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Client</th>
              <th style={styles.th}>Message</th>
              <th style={styles.th}>Source</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Latest</th>
              <th style={styles.th}>Intent</th>
              <th style={styles.th}>Risk</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.conversation_id}>
                <td style={styles.td}>{row.client_name}</td>
                <td style={styles.td}>{row.message_preview}</td>
                <td style={styles.td}>{row.source ?? "-"}</td>
                <td style={styles.td}>{row.status}</td>
                <td style={styles.td}>{new Date(row.latest_message_at).toLocaleString()}</td>
                <td style={styles.td}>Not classified yet</td>
                <td style={styles.td}>Not assessed yet</td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td style={styles.empty} colSpan={7}>
                  No inbox messages yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </main>
  );
}

const styles = {
  page: {
    padding: "32px",
    color: "#172026",
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
  },
  title: {
    margin: "0 0 20px",
    fontSize: "28px",
    fontWeight: 700,
  },
  tableWrap: {
    overflowX: "auto",
    border: "1px solid #d9e0e7",
    borderRadius: "8px",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    minWidth: "860px",
  },
  th: {
    padding: "12px 14px",
    background: "#f4f7f9",
    borderBottom: "1px solid #d9e0e7",
    fontSize: "13px",
    textAlign: "left",
  },
  td: {
    padding: "13px 14px",
    borderBottom: "1px solid #edf1f4",
    fontSize: "14px",
    verticalAlign: "top",
  },
  empty: {
    padding: "24px 14px",
    color: "#5d6b76",
    textAlign: "center",
  },
};
