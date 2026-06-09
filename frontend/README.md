# EventSense AI Frontend

The frontend app shell is not scaffolded yet. `src/MessageInbox.jsx` is a minimal React component for Feature 003 and currently reads the JWT access token from `localStorage.access_token`.

When the Vite app and auth flow are added, route this component at the inbox path and replace direct token access with the shared auth helper.
