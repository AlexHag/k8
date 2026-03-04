import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Home } from "./components/Home.tsx";
import { Chat } from "./components/Chat.tsx";
import { History } from "./components/History.tsx";

export function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/chat/:sessionId" element={<Chat />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
