import { Component, type ReactNode } from "react";

interface Props {
  what: string;
  children: ReactNode;
}

/** Keeps one broken part (e.g. a map) from blanking the whole app. */
export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="boundary" role="alert">
        <strong>The {this.props.what} hit a problem.</strong>
        <span className="muted"> {this.state.error.message}</span>
        <button className="btn btn--small" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}
