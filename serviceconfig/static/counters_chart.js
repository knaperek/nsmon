//var main_series_object = {
//    // color: color or number
//    // data: data,
//    color: 3,
//    label: "responding", 
//    // lines: specific lines options
//    // bars: specific bars options
//    // points: specific points options
//    // xaxis: number
//    // yaxis: number
//    // clickable: true,
//    // hoverable: true,
//};

var responding_serie_object = {
    label: "responding at all",
}
var responding_on_time_serie_object = {
    label: "responding on time",
}
var responding_ok_serie_object = {
    label: "answering OK",
}

var counters_main_chart_options = { 
    xaxis: {
        mode: "time", 
        minTickSize: [1, "minute"], 
        // tickColor: 1,
        // ticks: [5, "minute"],
        // tickSize: 1,

    },
	yaxis: {
		min: 0,
		max: 300,
    },
    // yaxis: { tickFormatter: function(v) { return v + " s"; }, },
    series: {
        lines: { 
            show: true,
            fill: true,
            steps: true,
        },
        // points: { show: true },
        // threshold: { below: 0.1, color: "rgb(200, 20, 30)" },
        points: { 
            radius: 2,
            // show: true,
        },
        bars: {
            // show: true,
        },
        stack: true,
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

counters_overview_chart_options = {
    series: {
        lines: { show: true, lineWidth: 1, fill: true, steps: true },
        stack: true,
    },
	xaxis: { mode: "time", },
    yaxis: { ticks: 4, min: 0, max: 300, }, // a little hack :-) I can't force it to use 2 ticks (it does not strictly follow this contstrain, but apparently tries not to be too far away from it
    selection: { mode: "x" },
};

function create_main_counters_chart(data) {
    var series = data['duration_serie']; // TODO: rename
    var d1 = [];
    var d2 = [];
    var d3 = [];
    for (var i = 0; i < series.length; i += 1) {
        d1.push([ series[i][0], series[i][1] ]);
        d2.push([ series[i][0], series[i][2] ]);
        d3.push([ series[i][0], series[i][3] ]);
       // d3.push([series[i][0], parseInt(Math.random() * 30)]);
    }


    // serie = $.extend(main_series_object, {data: data['duration_serie']}); // wrap data (simple list of points) into object with settings (defined above)
    // main_counters_chart = $.plot($("#counters_main_chart_div"), [serie], counters_main_chart_options);
 /*
    var d1 = [];
    for (var i = 0; i <= 10; i += 1)
        d1.push([i, parseInt(Math.random() * 30)]);

    var d2 = [];
    for (var i = 0; i <= 10; i += 1)
        d2.push([i, parseInt(Math.random() * 30)]);

    var d3 = [];
    for (var i = 0; i <= 10; i += 1)
        d3.push([i, parseInt(Math.random() * 30)]);
*/
    s1 = $.extend(responding_serie_object, {data: d1});
    s2 = $.extend(responding_on_time_serie_object, {data: d2});
    s3 = $.extend(responding_ok_serie_object, {data: d3});
    main_counters_chart = $.plot($("#counters_main_chart_div"), [s1, s2, s3], counters_main_chart_options);
    
    $("#counters_aggregation_info").html(data['aggregation'] ? "Data series aggregated by Min on every<b> " + data['aggregation'] + "</b>" : ""); // set info text about aggregation period used
};

function reload_main_counters_chart(url) {
    $.ajax({
        url: url,
        method: 'GET',
        dataType: 'json',
        success: create_main_counters_chart
    });
};

function reload_overview_counters_chart() {
    $.ajax({
        url: COUNTERS_CHARTS_DATA_FETCH_URL_BASE,
        method: 'GET',
        dataType: 'json',
        success: function(data) {
            var series = data['duration_serie']; // TODO: rename
            var d1 = [];
            var d2 = [];
            var d3 = [];
            for (var i = 0; i < series.length; i += 1) {
                d1.push([ series[i][0], series[i][1] ]);
                d2.push([ series[i][0], series[i][2] ]);
                d3.push([ series[i][0], series[i][3] ]);
                // d3.push([series[i][0], parseInt(Math.random() * 30)]);
            }

            //counters_overview_chart = $.plot($("#counters_overview_chart_div"), [data['duration_serie']], counters_overview_chart_options);
            counters_overview_chart = $.plot($("#counters_overview_chart_div"), [d1, d2, d3], counters_overview_chart_options);

            create_main_counters_chart(data); // optimalization: for single request on page load to be sufficient
        }
    });
};

function init_counters_charts() {
    $("#counters_main_chart_div").unbind();
    $("#counters_overview_chart_div").unbind();

    reload_overview_counters_chart();

    // bind handler for main chart
    $("#counters_main_chart_div").bind("plotselected", function(event, ranges) {
        // recreate main chart with data from selected interval
        reload_main_counters_chart(COUNTERS_CHARTS_DATA_FETCH_URL_BASE + Math.round(ranges.xaxis.from) + "-" + Math.round(ranges.xaxis.to));

        // don't fire event on the overview to prevent eternal loop
        counters_overview_chart.setSelection(ranges, true); // counters_overview_chart is global variable
    });

    // bind handler for overview chart
    $("#counters_overview_chart_div").bind("plotselected", function(event, ranges) {
        main_counters_chart.setSelection(ranges); // main_counters_chart is global variable
    });
};

function insert_counters_charts(DOM_element_selector, data_fetch_url_base) { // Public function for inserting counters chart(s) in the document

    $(DOM_element_selector).html('');
    $(DOM_element_selector).append('<div id="counters_main_chart_div" class="main_chart_div"></div>');
    $(DOM_element_selector).append('<div id="counters_overview_chart_div" class="overview_chart_div"></div>');
    $(DOM_element_selector).append('<div id="counters_aggregation_info" class="chart_aggregation_info">Used aggregation:</div>');
    $(DOM_element_selector).append('<div class="chart_button_reset"><button id="counters_button_reset">Reset</button></div>');
									//<div class="chart_button_reset"><button id="duration_button_reset">Reset</button></div>'

    COUNTERS_CHARTS_DATA_FETCH_URL_BASE = data_fetch_url_base;

    init_counters_charts();
    $("#counters_button_reset").click(function(event) {
        init_counters_charts()
    });
}



