var main_duration_serie_object = {
    // color: color or number
    // data: data,
    color: 3,
    label: "latency (sec.)", 
    // lines: specific lines options
    // bars: specific bars options
    // points: specific points options
    // xaxis: number
    // yaxis: number
    clickable: true,
    hoverable: true,
    // threshold: { below: 2, color: "rgb(200, 20, 30)" },
//     threshold: { below: 2.5, color: "rgb(200, 20, 30)" },
    // shadowSize: number
};

var duration_main_chart_options = { 
    xaxis: {
        mode: "time", 
        minTickSize: [1, "minute"], 
        // tickColor: 1,
        // ticks: [5, "minute"],
        // tickSize: 1,
    },
	yaxis: { min: 0, },

    // yaxis: { tickFormatter: function(v) { return v + " s"; }, },
    series: {
        lines: { 
            show: true,
            fill: true,
            // steps: true,
        },
        // points: { show: true },
        // threshold: { below: 0.1, color: "rgb(200, 20, 30)" },
        points: { 
            radius: 2,
            show: true,
        },
        bars: {
            // show: true,
        },
    },

  // lines: { show: true, fill: true, fillColor: "rgba(255, 255, 255, 0.8)" },
  // points: { show: true, fill: false },
    selection: {
        mode: "x"
    },
    grid: {
        // aboveData: true,
        // color: 1,
        // labelMargin: 50,
        // borderWidth: 0,
        hoverable: true,
        // clickable: true,
    },
};

duration_overview_chart_options = {
    series: {
        lines: { show: true, lineWidth: 1 },
//          shadowSize: 0,
        color: 3,
    },
    xaxis: { mode: "time", },
    yaxis: { ticks: 1, min: 0, }, // a little hack :-) I can't force it to use 2 ticks (it does not strictly follow this contstrain, but apparently tries not to be too far away from it
    selection: { mode: "x" },
};

function create_main_duration_chart(data) {
    serie = $.extend(main_duration_serie_object, {data: data['duration_serie']}); // wrap data (simple list of points) into object with settings (defined above)
    main_duration_chart = $.plot($("#duration_main_chart_div"), [serie], duration_main_chart_options);
    $("#duration_aggregation_info").html(data['aggregation'] ? "Data serie aggregated by Max on every<b> " + data['aggregation'] + "</b>" : ""); // set info text about aggregation period used
};

function reload_main_duration_chart(url) {
    $.ajax({
        url: url,
        method: 'GET',
        dataType: 'json',
        success: create_main_duration_chart
    });
};

function reload_overview_duration_chart() {
    $.ajax({
        url: DURATION_CHARTS_DATA_FETCH_URL_BASE,
        method: 'GET',
        dataType: 'json',
        success: function(data) {
            duration_overview_chart = $.plot($("#duration_overview_chart_div"), [data['duration_serie']], duration_overview_chart_options);
            create_main_duration_chart(data); // optimalization: for single request on page load to be sufficient
        }
    });
};

function init_duration_charts() {
    $("#duration_main_chart_div").unbind();
    $("#duration_overview_chart_div").unbind();

    reload_overview_duration_chart();
    // reload_main_duration_chart("/admin/serviceconfig/testresult/duration-json2/"); // disabled due to optimalization (single request on page load)

    // bind handler for main chart
    $("#duration_main_chart_div").bind("plotselected", function(event, ranges) {
        // recreate main chart with data from selected interval
        reload_main_duration_chart(DURATION_CHARTS_DATA_FETCH_URL_BASE + Math.round(ranges.xaxis.from) + "-" + Math.round(ranges.xaxis.to));

        // don't fire event on the overview to prevent eternal loop
        duration_overview_chart.setSelection(ranges, true); // duration_overview_chart is global variable
    });

    // bind handler for overview chart
    $("#duration_overview_chart_div").bind("plotselected", function(event, ranges) {
        main_duration_chart.setSelection(ranges); // main_duration_chart is global variable
    });
};

function insert_duration_charts(DOM_element_selector, data_fetch_url_base) { // Public function for inserting duration chart(s) in the document

    $(DOM_element_selector).html('');
    // $(DOM_element_selector).append('<div id="duration_main_chart_div" style="width:600px;height:300px" class="main_chart_div"></div>');
    $(DOM_element_selector).append('<div id="duration_main_chart_div" class="main_chart_div"></div>');
    $(DOM_element_selector).append('<div id="duration_overview_chart_div" class="overview_chart_div"></div>');
    $(DOM_element_selector).append('<div id="duration_aggregation_info" class="chart_aggregation_info">Used aggregation:</div>');
    $(DOM_element_selector).append('<div class="chart_button_reset"><button id="duration_button_reset">Reset</button></div>');

    DURATION_CHARTS_DATA_FETCH_URL_BASE = data_fetch_url_base;

    init_duration_charts();
    $("#duration_button_reset").click(function(event) {
        init_duration_charts()
    });
}



