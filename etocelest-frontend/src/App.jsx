import { Routes, Route, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import NavBar from "./components/NavBar";
import Footer from "./components/Footer";
import AmbientBackground from "./components/AmbientBackground";
import Home from "./pages/Home";
import NewSession from "./pages/NewSession";
import DebateRoom from "./pages/DebateRoom";
import Verdict from "./pages/Verdict";
import History from "./pages/History";
import HowItWorks from "./pages/HowItWorks";

function PageTransition({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
    >
      {children}
    </motion.div>
  );
}

export default function App() {
  const location = useLocation();

  return (
    <div className="min-h-screen flex flex-col font-sans text-ink-900">
      <AmbientBackground />
      <NavBar />
      <main className="flex-1">
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<PageTransition><Home /></PageTransition>} />
            <Route path="/new" element={<PageTransition><NewSession /></PageTransition>} />
            <Route path="/debate/:sessionId" element={<PageTransition><DebateRoom /></PageTransition>} />
            <Route path="/verdict/:sessionId" element={<PageTransition><Verdict /></PageTransition>} />
            <Route path="/history" element={<PageTransition><History /></PageTransition>} />
            <Route path="/how-it-works" element={<PageTransition><HowItWorks /></PageTransition>} />
          </Routes>
        </AnimatePresence>
      </main>
      <Footer />
    </div>
  );
}
