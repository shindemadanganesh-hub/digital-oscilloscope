import json
import streamlit as st
import pandas as pd
import plotly.express as px


st.set_page_config(
    page_title="DRS Digital Oscilloscope",
    layout="wide"
)

st.title("DRS Digital Oscilloscope")
st.markdown("Upload a CSV file and visualize received signals by asset over time.")

st.markdown(
    "<style>"
    ".js-plotly-plot .scatterlayer .point { cursor: pointer !important; }"
    ".js-plotly-plot .scatterlayer .point:hover { cursor: pointer !important; }"
    ".signal-panel { resize: horizontal; overflow: auto; min-width: 260px; max-width: 90vw; max-height: 78vh; border: 1px solid #d0d7de; border-radius: 12px; padding: 14px; background: white; box-shadow: 0 10px 24px rgba(0,0,0,0.1); }"
    ".signal-panel table { width: 100%; border-collapse: collapse; }"
    ".signal-panel th, .signal-panel td { border: 1px solid #d0d7de; padding: 8px; text-align: left; }"
    ".signal-panel th { background: #f6f8fa; }"
    "</style>",
    unsafe_allow_html=True,
)

st.subheader("Periodic CSV")
periodic_file = st.file_uploader("Upload periodic CSV", type=["csv"], key="periodic_uploader")

st.subheader("Events CSV")
event_file = st.file_uploader("Upload events CSV", type=["csv"], key="event_uploader")

def parse_signal_payload(payload, first_only=False):
    if pd.isna(payload):
        return []

    if isinstance(payload, str):
        payload_text = payload.strip()
        if not payload_text:
            return []
        try:
            parsed_payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return []
    else:
        parsed_payload = payload

    if isinstance(parsed_payload, dict):
        parsed_payload = [parsed_payload]
    if not isinstance(parsed_payload, list):
        return []

    if first_only and parsed_payload:
        parsed_payload = [parsed_payload[0]]

    signal_rows = []
    for item in parsed_payload:
        if isinstance(item, dict):
            signal_rows.append({
                "Signal": item.get("name", "Unnamed"),
                "Value": item.get("value", ""),
                "Unit": item.get("unit") or "—",
            })
    return signal_rows

def prepare_dataset(df, source):
    if source == "Periodic":
        timestamp_col = df.columns[0]
        asset_col = df.columns[4]
        signals_col = next((col for col in df.columns if str(col).strip().lower() == "signals"), None)
        if signals_col is None and len(df.columns) > 7:
            signals_col = df.columns[7]
        first_signal_only = False
        st.subheader("Column Mapping Assumption")
        st.info("Column A = Timestamp (UTC), Column E = AncestorAssetId, Column H = Signals")
    else:
        timestamp_col = df.columns[9]
        asset_col = df.columns[4]
        signals_col = df.columns[13] if len(df.columns) > 13 else None
        first_signal_only = True
        st.subheader("Column Mapping Assumption")
        st.info("Column E = AncestorAssetId, Column J = Timestamp (UTC), Column N = Signals (use first entry)")

    if signals_col is None:
        return None, None, None, None, None

    df[timestamp_col] = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce")
    df = df.dropna(subset=[timestamp_col]).reset_index(drop=True)
    df[asset_col] = df[asset_col].astype(str)
    df["date"] = df[timestamp_col].dt.date

    return df, timestamp_col, asset_col, signals_col, first_signal_only

source_data = {}

if periodic_file is not None:
    periodic_df = pd.read_csv(periodic_file, low_memory=False)
    (
        periodic_df,
        periodic_timestamp_col,
        periodic_asset_col,
        periodic_signals_col,
        periodic_first_signal_only,
    ) = prepare_dataset(periodic_df, source="Periodic")
    if periodic_signals_col is None:
        st.error("The periodic file does not contain a signals column.")
        st.stop()
    source_data["Periodic"] = {
        "df": periodic_df,
        "timestamp_col": periodic_timestamp_col,
        "asset_col": periodic_asset_col,
        "signals_col": periodic_signals_col,
        "first_signal_only": periodic_first_signal_only,
    }

if event_file is not None:
    event_df = pd.read_csv(event_file, low_memory=False)
    (
        event_df,
        event_timestamp_col,
        event_asset_col,
        event_signals_col,
        event_first_signal_only,
    ) = prepare_dataset(event_df, source="Events")
    if event_signals_col is None:
        st.error("The events file does not contain a signals column.")
        st.stop()
    source_data["Events"] = {
        "df": event_df,
        "timestamp_col": event_timestamp_col,
        "asset_col": event_asset_col,
        "signals_col": event_signals_col,
        "first_signal_only": event_first_signal_only,
    }

if not source_data:
    st.info("Upload a periodic file or an events file to begin.")
    st.stop()

source_options = list(source_data.keys())
selected_source = source_options[0]
if len(source_options) > 1:
    selected_source = st.sidebar.selectbox("Dataset to inspect", source_options, index=0)

selected_source_data = source_data[selected_source]

if "selected_day" not in st.session_state:
    st.session_state.selected_day = None
if "detail_popup_open" not in st.session_state:
    st.session_state.detail_popup_open = False
if "detail_popup_row" not in st.session_state:
    st.session_state.detail_popup_row = None

timestamp_col = selected_source_data["timestamp_col"]
asset_col = selected_source_data["asset_col"]
signals_col = selected_source_data["signals_col"]
first_signal_only = selected_source_data["first_signal_only"]

min_date = selected_source_data["df"]["date"].min()
max_date = selected_source_data["df"]["date"].max()

st.sidebar.header("Filters")
asset_ids = sorted(selected_source_data["df"][asset_col].dropna().astype(str).unique())
selected_asset = st.sidebar.selectbox(
    "AncestorAssetId",
    asset_ids,
    index=0 if asset_ids else 0,
    help="Choose one asset ID to display."
)
selected_assets = [selected_asset] if selected_asset else []

date_range = st.sidebar.date_input(
    "Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

plot_df = selected_source_data["df"].copy()
plot_df = plot_df.sort_values(timestamp_col).reset_index(drop=True)
filtered_df = plot_df.copy()
if selected_assets:
    filtered_df = filtered_df[filtered_df[asset_col].astype(str).isin(selected_assets)]
if len(date_range) == 2:
    start_date, end_date = date_range
    filtered_df = filtered_df[
        (filtered_df["date"] >= start_date)
        & (filtered_df["date"] <= end_date)
    ]

if filtered_df.empty:
    st.warning("No data found for selected filters.")
    st.stop()

source_first_signal_only = {
    source_name: source_info["first_signal_only"]
    for source_name, source_info in source_data.items()
}

overview_counts = []
combined_dfs = []
for source_name, source_info in source_data.items():
    source_df = source_info["df"].copy()
    source_df["source"] = source_name
    source_df["asset"] = source_df[source_info["asset_col"]].astype(str)
    source_df["timestamp"] = source_df[source_info["timestamp_col"]]
    source_df["signals"] = source_df[source_info["signals_col"]]
    if selected_assets:
        source_df = source_df[source_df["asset"].isin(selected_assets)]
    if len(date_range) == 2:
        source_df = source_df[
            (source_df["date"] >= start_date)
            & (source_df["date"] <= end_date)
        ]
    daily_counts = (
        source_df.groupby("date")
        .size()
        .reset_index(name="records")
    )
    daily_counts["source"] = source_name
    overview_counts.append(daily_counts)
    combined_dfs.append(source_df[["timestamp", "asset", "signals", "date", "source"]])

overview_df = pd.concat(overview_counts, ignore_index=True)
combined_df = pd.concat(combined_dfs, ignore_index=True) if combined_dfs else pd.DataFrame(
    columns=["timestamp", "asset", "signals", "date", "source"]
)

plot_df = filtered_df[[timestamp_col, asset_col, signals_col]].copy()
plot_df[asset_col] = plot_df[asset_col].astype(str)
plot_df = plot_df.sort_values(timestamp_col).reset_index(drop=True)
plot_df["date"] = plot_df[timestamp_col].dt.date

overview_fig = px.line(
    overview_df,
    x="date",
    y="records",
    color="source",
    markers=True,
    title=f"Daily record counts for {selected_asset}",
    labels={"date": "Date", "records": "Records", "source": "Source"},
    color_discrete_map={"Periodic": "#1f77b4", "Events": "#d62728"},
)
overview_fig.update_traces(
    mode="lines+markers",
    marker=dict(size=10),
)
overview_fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Records",
    height=520,
    hovermode="closest",
    xaxis=dict(rangeslider=dict(visible=True), type="date", showgrid=True),
)

st.subheader("Daily Overview")
overview_selection = st.plotly_chart(
    overview_fig,
    key="daily_overview",
    on_select="rerun",
    selection_mode="points",
    use_container_width=True,
)

if overview_selection and overview_selection.selection and overview_selection.selection.point_indices:
    selected_index = overview_selection.selection.point_indices[0]
    if selected_index is not None and selected_index < len(overview_df):
        st.session_state.selected_day = overview_df.iloc[selected_index]["date"]
        st.session_state.detail_popup_open = False
        st.session_state.detail_popup_row = None

if st.session_state.selected_day is not None:
    selected_day = st.session_state.selected_day
    day_df = combined_df[combined_df["date"] == selected_day].copy()
    day_df = day_df.sort_values("timestamp").reset_index(drop=True)
    day_df["record_num"] = day_df.index + 1

    start_of_day = pd.Timestamp(selected_day).tz_localize("UTC")
    end_of_day = start_of_day + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    detail_fig = px.scatter(
        day_df,
        x="timestamp",
        y="record_num",
        color="source",
        color_discrete_map={"Periodic": "#1f77b4", "Events": "#d62728"},
        custom_data=["source", "asset"],
        title=f"Intraday timeline for {selected_day} ({len(day_df)} records)",
        labels={"record_num": "Record #", "timestamp": "Timestamp (UTC)", "source": "Source"},
    )
    detail_fig.update_traces(
        marker=dict(size=10),
        hovertemplate="Time: %{x|%H:%M:%S}<br>Source: %{customdata[0]}<br>Asset: %{customdata[1]}<br>Record #: %{y}<extra></extra>",
    )
    detail_fig.update_layout(
        xaxis_title="Time (UTC)",
        yaxis_title="Record index",
        height=520,
        hovermode="closest",
        xaxis=dict(range=[start_of_day, end_of_day], tickformat="%H:%M", showgrid=True),
    )

    left_col, right_col = st.columns([3, 1])

    with left_col:
        st.subheader(f"Intraday detail for {selected_day}")
        detail_selection = st.plotly_chart(
            detail_fig,
            key="intraday_detail",
            on_select="rerun",
            selection_mode="points",
            use_container_width=True,
        )

        if detail_selection and detail_selection.selection and detail_selection.selection.point_indices:
            point_index = detail_selection.selection.point_indices[0]
            if point_index is not None and point_index < len(day_df):
                selected_row = day_df.iloc[point_index]
                signal_rows = parse_signal_payload(
                    selected_row["signals"],
                    first_only=source_first_signal_only.get(selected_row["source"], False),
                )
                st.session_state.detail_popup_open = True
                st.session_state.detail_popup_row = {
                    "asset": selected_row["asset"],
                    "timestamp": selected_row["timestamp"],
                    "signals": signal_rows,
                }

    with right_col:
        panel = st.expander("Signal details", expanded=st.session_state.detail_popup_open)
        with panel:
            if st.session_state.detail_popup_open and st.session_state.detail_popup_row:
                row = st.session_state.detail_popup_row
                if st.button("Close panel", key="close_detail_popup"):
                    st.session_state.selected_day = None
                    st.session_state.detail_popup_open = False
                    st.session_state.detail_popup_row = None

                signal_html = (
                    "<div class='signal-panel'>"
                    f"<p><strong>Asset:</strong> {row['asset']}</p>"
                    f"<p><strong>Timestamp:</strong> {row['timestamp']}</p>"
                    "<hr/>"
                    f"{pd.DataFrame(row['signals']).to_html(index=False, border=0)}"
                    "</div>"
                )
                st.markdown(signal_html, unsafe_allow_html=True)
            else:
                st.info("Select an intraday point to view its signals here.")

    if st.button("Clear selected day", key="clear_selected_day"):
        st.session_state.selected_day = None
        st.session_state.detail_popup_open = False
        st.session_state.detail_popup_row = None
else:
    st.info("Select a date point in the daily overview to see the full intraday timeline for that day.")

col1, col2 = st.columns(2)
with col1:
    st.metric("Selected asset", selected_asset)
with col2:
    st.metric("Records", len(filtered_df))

st.subheader("Filtered Data")
st.dataframe(filtered_df, use_container_width=True)
