# -*- coding: utf-8 -*-

# make pyflakes happy, define interface for import *
__all__ = ['request', 'make_response', 'flash', 'url_for', 'render_template',
           'send_file', 'list_to_factored_poly_otherorder',
           'list_factored_to_factored_poly_otherorder',
           'key_for_numerically_sort', 'coeff_to_poly',
           'coeff_to_power_series', 'display_multiset', 'pair2complex',
           'round_CBF_to_half_int', 'str_to_CBF', 'to_dict', 'display_float',
           'display_complex', 'round_to_half_int', 'splitcoeff', 'comma',
           'format_percentage', 'signtocolour', 'rgbtohex', 'pol_to_html',
           'web_latex', 'web_latex_ideal_fact', 'web_latex_split_on',
           'web_latex_split_on_pm', 'web_latex_split_on_re', 'display_knowl',
           'teXify_pol', 'add_space_if_positive',
           'bigint_knowl', 'too_big', 'make_bigint', 'bigpoly_knowl',
           'factor_base_factor', 'factor_base_factorization_latex',
           'polyquo_knowl', 'web_latex_poly', 'list_to_latex_matrix',
           'code_snippet_knowl',
           'Pagination',
           'debug', 'flash_error',
           'ajax_url',
           'image_callback', 'encode_plot',
           'KeyedDefaultDict', 'make_tuple', 'range_formatter',
           'Configuration',
           'names_and_urls', 'name_and_object_from_url',
           'datetime_to_timestamp_in_ms', 'timestamp_in_ms_to_datetime',
           'reraise']

from flask import (request, make_response, flash, url_for,
                   render_template, send_file)

from .utilities import (
    list_to_factored_poly_otherorder,
    list_factored_to_factored_poly_otherorder,
    key_for_numerically_sort, coeff_to_poly, coeff_to_power_series,
    display_multiset, pair2complex, round_CBF_to_half_int, str_to_CBF,
    to_dict, display_float, display_complex, round_to_half_int,
    splitcoeff, comma, format_percentage, signtocolour, rgbtohex, pol_to_html,
    web_latex, web_latex_ideal_fact, web_latex_split_on, web_latex_split_on_pm,
    web_latex_split_on_re, display_knowl, bigint_knowl, too_big, make_bigint,
    teXify_pol, add_space_if_positive,
    bigpoly_knowl, factor_base_factor, factor_base_factorization_latex,
    polyquo_knowl, web_latex_poly, list_to_latex_matrix, code_snippet_knowl,
    Pagination,
    debug, flash_error, 
    ajax_url,  # try to eliminate?
    image_callback, encode_plot,
    KeyedDefaultDict, make_tuple, range_formatter,
    datetime_to_timestamp_in_ms, timestamp_in_ms_to_datetime)

from .search_boxes import (
    BasicSpacer,
    SearchArray,
    TextBox,
    SelectBox,
)

from .downloader import Downloader
from .config import Configuration
from .names_and_urls import names_and_urls, name_and_object_from_url
from .reraise import reraise
