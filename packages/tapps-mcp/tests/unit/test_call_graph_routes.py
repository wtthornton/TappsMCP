"""Tests for HTTP route -> handler edges (TAP-4532).

Covers FastAPI decorator routes (Python ``ast``), React Router JSX routes
(TypeScript tree-sitter), the two query directions (handler-for-path,
routes-for-handler / blast radius), and the deterministic contract: dynamic /
unresolvable route registration is omitted, never guessed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_analyze_ts import HAS_TREE_SITTER
from tapps_mcp.project.call_graph_queries import (
    query_route_handler,
    query_routes_for_handler,
)
from tapps_mcp.project.call_graph_routes import (
    handlers_for_path,
    routes_for_handler,
)


def _write(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


class TestFastAPIRoutes:
    def test_decorator_routes_produce_edges(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/api.py",
            """
from fastapi import APIRouter, FastAPI

app = FastAPI()
router = APIRouter()


@app.get("/health")
def health():
    return {"ok": True}


@router.post("/users/{user_id}")
async def create_user(user_id: int):
    return user_id
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        by_handler = {r.handler_symbol: r for r in index.routes}

        assert "app.api.health" in by_handler
        health = by_handler["app.api.health"]
        assert health.method == "GET"
        assert health.path == "/health"
        assert health.framework == "fastapi"
        assert health.file_path == "app/api.py"
        assert health.line == 8

        create = by_handler["app.api.create_user"]
        assert create.method == "POST"
        assert create.path == "/users/{user_id}"

    def test_generic_route_decorator_recorded(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/legacy.py",
            """
from fastapi import APIRouter

router = APIRouter()


@router.route("/legacy")
def legacy():
    return "x"
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        routes = [r for r in index.routes if r.handler_symbol == "app.legacy.legacy"]
        assert len(routes) == 1
        assert routes[0].method == "ROUTE"
        assert routes[0].path == "/legacy"

    def test_dynamic_path_is_omitted_not_guessed(self, tmp_path: Path) -> None:
        # Non-literal decorator path -> no RouteEdge (deterministic contract).
        _write(
            tmp_path,
            "app/dynamic.py",
            """
from fastapi import FastAPI

app = FastAPI()


def register(path):
    @app.get(path)
    def handler():
        return 1

    return handler
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert index.routes == []

    def test_non_route_decorator_ignored(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/deco.py",
            """
import functools


@functools.cache
def cached():
    return 1
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert index.routes == []


@pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter TypeScript grammar not installed")
class TestReactRouterRoutes:
    def test_jsx_route_elements_produce_edges(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/App.tsx",
            """
import { Routes, Route } from "react-router-dom";
import Home from "./Home";
import { About } from "./pages/About";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/about" element={<About />} />
    </Routes>
  );
}
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        routes = [r for r in index.routes if r.framework == "react-router"]
        by_path = {r.path: r for r in routes}

        assert "/" in by_path
        assert by_path["/"].method == "ROUTE"
        # Default import from ./Home resolves the component to its module.
        assert by_path["/"].handler_symbol == "Home.Home"
        assert by_path["/"].file_path == "src/App.tsx"

        assert "/about" in by_path
        # Named relative import -> qualified to the target module.
        assert by_path["/about"].handler_symbol == "pages/About.About"

    def test_unimported_component_keeps_bare_name(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/Routes.tsx",
            """
import { Route } from "react-router-dom";

function AppRoutes() {
  return <Route path="/x" element={<LocalOnly />} />;
}
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        routes = [r for r in index.routes if r.framework == "react-router"]
        assert len(routes) == 1
        # No in-repo import -> bare component name, never a fabricated module.
        assert routes[0].handler_symbol == "LocalOnly"
        assert routes[0].path == "/x"

    def test_spread_element_is_omitted_not_guessed(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/Spread.tsx",
            """
import { Route } from "react-router-dom";

function AppRoutes(routeDef: any) {
  return <Route path="/dyn" element={routeDef.el} />;
}
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        # element is not a nameable JSX component -> no RouteEdge.
        assert [r for r in index.routes if r.framework == "react-router"] == []

    def test_object_literal_router_form_deferred(self, tmp_path: Path) -> None:
        # createBrowserRouter object form is deferred for v1 — nothing emitted,
        # never guessed. (Documented deferral in call_graph_routes.py.)
        _write(
            tmp_path,
            "src/router.tsx",
            """
import { createBrowserRouter } from "react-router-dom";
import Home from "./Home";

const router = createBrowserRouter([
  { path: "/", element: <Home /> },
]);
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert [r for r in index.routes if r.framework == "react-router"] == []


class TestRouteQueries:
    def test_handler_for_path(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/api.py",
            """
from fastapi import FastAPI

app = FastAPI()


@app.get("/items/{item_id}")
def read_item(item_id: int):
    return item_id
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_route_handler(index, "/items/{item_id}")
        assert result["found"] is True
        assert result["handlers"][0]["handler_symbol"] == "app.api.read_item"

        miss = query_route_handler(index, "/nope")
        assert miss["found"] is False
        assert miss["handlers"] == []

    def test_routes_for_handler_blast_radius(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/api.py",
            """
from fastapi import FastAPI

app = FastAPI()


@app.get("/a")
@app.post("/a")
def shared():
    return 1
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_routes_for_handler(index, "shared")
        assert result["found"] is True
        methods = sorted(r["method"] for r in result["routes"])
        assert methods == ["GET", "POST"]

        # Exact qualified name also matches.
        exact = query_routes_for_handler(index, "app.api.shared")
        assert exact["found"] is True
        assert len(exact["routes"]) == 2

    def test_query_helpers_direct(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app/api.py",
            """
from fastapi import FastAPI

app = FastAPI()


@app.get("/ping")
def ping():
    return "pong"
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert len(handlers_for_path(index.routes, "/ping")) == 1
        assert len(routes_for_handler(index.routes, "ping")) == 1
        assert routes_for_handler(index.routes, "") == []


class TestRoutesPersisted:
    def test_routes_survive_cache_round_trip(self, tmp_path: Path) -> None:
        from tapps_mcp.project.call_graph import load_call_graph_index

        _write(
            tmp_path,
            "app/api.py",
            """
from fastapi import FastAPI

app = FastAPI()


@app.delete("/thing/{id}")
def drop(id: int):
    return id
""",
        )
        built = build_call_graph_index(tmp_path, force_rebuild=True)
        assert built.routes

        loaded = load_call_graph_index(tmp_path)
        assert loaded is not None
        assert len(loaded.routes) == 1
        assert loaded.routes[0].method == "DELETE"
        assert loaded.routes[0].path == "/thing/{id}"
        assert loaded.routes[0].handler_symbol == "app.api.drop"
